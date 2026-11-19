#!/usr/bin/env python3
"""BU1-SDK 规则快照刷新执行器。

子命令：

- ``plan``：经 redmine/scripts/redmine.py 读在线 Wiki，生成候选临时文件、输出差异
  与在线全文供审阅，并把候选登记成待确认动作（confirm-gate）。
- ``apply``：取得事务锁后重新计算现场摘要，gate.authorize() 通过才逐个原子替换
  reference；全部替换并复核成功后清理事务标记。
- ``abort``：仅当现场哈希证明两个 reference 都未被替换时才清理事务。
- ``status``：只读报告事务标记判定出的中断状态，不做任何修改。

业务技能（commit-gerrit、update-issue-conclusion）只读取本地 reference 快照，
不感知本脚本的事务标记。本脚本不签发确认凭据：凭据由宿主侧 confirm-gate 在
用户明确选择确认后写入，见 confirm-gate/README.md。

所有哈希都是原始字节的 SHA-256（不做换行归一化），与 git hash-object 可比对。
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SKILL_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_DIR.parent
GATE_PATH = REPO_ROOT / "confirm-gate" / "scripts" / "gate.py"
PENDING_PATH = SKILL_DIR / ".refresh.pending"
PENDING_LOCK_PATH = SKILL_DIR / ".refresh.pending.lock"
KIND = "refresh-bu1-sdk-rules"
DEFAULT_CHECKED_BY = "luyong-AI"
DEFAULT_REDMINE_URL = "https://git.nationalchip.com/redmine"
PROJECT = "bu1-sdk"

# 快照 = 一个 reference 文件 + 写入它的来源页面。SNAPSHOTS 的顺序即替换顺序。
SNAPSHOTS: dict[str, dict[str, Any]] = {
    "commit-gerrit": {
        "reference": "commit-gerrit/references/bu1-sdk-gerrit-rules.md",
        "pages": ["Gerrit使用规则", "Gerrit补丁生成细则"],
    },
    "update-issue-conclusion": {
        "reference": "update-issue-conclusion/references/bu1-sdk-conclusion-rules.md",
        "pages": ["Redmine使用规则"],
    },
}
# 页面 URL 里已百分号编码的标题，与 SKILL.md 登记的 API 地址一致。
PAGE_URL_PATH = {
    "Gerrit使用规则": "Gerrit%E4%BD%BF%E7%94%A8%E8%A7%84%E5%88%99",
    "Gerrit补丁生成细则": "Gerrit%E8%A1%A5%E4%B8%81%E7%94%9F%E6%88%90%E7%BB%86%E5%88%99",
    "Redmine使用规则": "Redmine%E4%BD%BF%E7%94%A8%E8%A7%84%E5%88%99",
}

META_KEYS = ("source_version", "source_updated_on", "checked_at", "checked_by")
META_LINE = {key: re.compile(rf"^- `{key}: (.+)`$") for key in META_KEYS}
SOURCE_LIST_ANCHOR = "当前快照整理自以下 Redmine REST Wiki API 页面："
SOURCE_LIST_LINE = re.compile(r"^- `GET \S+`：页面 `.+`，快照来源 version `\d+`，`updated_on` 为 `.+`。$")


class RefreshError(Exception):
    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


# ---------------------------------------------------------------- 基础工具


def _emit(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(text: str) -> dt.datetime | None:
    """只接受带明确 UTC 时区（Z 或 +00:00）的可解析时间。"""
    if not isinstance(text, str) or not text:
        return None
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        return None
    return parsed


def sha256_bytes(path: Path) -> str:
    """文件的原始字节 SHA-256；不存在时抛错。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def read_raw(path: Path) -> str:
    """按原样读取文本：不做换行归一化，\r\n 保持 \r\n。"""
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.read()
    except OSError as error:
        raise RefreshError("unreadable", f"读不到 {path}：{error}") from None


def write_atomic(path: Path, text: str) -> None:
    """同目录临时文件 + rename，原子写入；不转换换行。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 0o644
    try:
        mode = os.stat(path).st_mode & 0o777
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def remove_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def remove_checked(path: Path) -> bool:
    """删除并在失败时如实报告；返回是否已不存在。"""
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return True
    except OSError as error:
        print(f"警告：无法删除 {path}：{error}", file=sys.stderr)
        return False


def reference_path(snapshot: str) -> Path:
    return (REPO_ROOT / SNAPSHOTS[snapshot]["reference"]).resolve()


def _load_gate():
    import importlib.util

    spec = importlib.util.spec_from_file_location("confirm_gate_shared", GATE_PATH)
    assert spec and spec.loader, GATE_PATH
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def pending_lock() -> Iterator[None]:
    """串行化会写 reference / 事务标记的临界区，避免两个执行进程交错。"""
    PENDING_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_LOCK_PATH, "a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RefreshError(
                "busy",
                "另一个刷新进程正在运行（事务锁被占用）。停止并报告，不要并行重试。",
            ) from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_pending() -> dict[str, Any]:
    data = json.loads(read_raw(PENDING_PATH))
    if not isinstance(data, dict) or data.get("kind") != KIND:
        raise RefreshError("bad_pending", f"{PENDING_PATH} 不是本技能的事务标记。")
    return data


def _pending_complete(pending: dict[str, Any]) -> str | None:
    """返回缺失的字段名；完整返回 None。"""
    for field in ("checked_at", "checked_by", "pages"):
        if field not in pending:
            return field
    snapshots = pending.get("snapshots")
    if not isinstance(snapshots, dict) or set(snapshots) != set(SNAPSHOTS):
        return "snapshots"
    for state in snapshots.values():
        for field in ("sha256_before", "candidate_sha256", "temp"):
            if field not in state:
                return f"snapshots[].{field}"
    return None


# ---------------------------------------------------------------- 快照内容


def current_metadata(reference_text: str) -> dict[str, str | None]:
    """解析 reference 现有的元数据行；缺失的项为 None。"""
    found: dict[str, str | None] = {}
    for key in META_KEYS:
        for line in reference_text.splitlines():
            match = META_LINE[key].match(line)
            if match:
                found[key] = match.group(1)
                break
    return found


def parse_source_versions(value: str | None) -> dict[str, int | None]:
    """把 source_version 行拆成 页面名 -> 版本；解析不了的项为 None。"""
    if not value:
        return {}
    versions: dict[str, int | None] = {}
    for item in value.split(";"):
        name, separator, raw = item.strip().partition("=")
        raw_version = raw if separator else name
        title = name if separator else None
        try:
            version = int(raw_version)
        except ValueError:
            version = None
        if title:
            versions[title] = version
        else:
            versions["*"] = version
    return versions


def strip_metadata(text: str) -> str:
    """去掉随刷新变动的元数据行（四个元数据 bullet 和来源清单），留下规则正文。"""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.rstrip("\r\n") == SOURCE_LIST_ANCHOR:
            index += 1
            while index < len(lines) and SOURCE_LIST_LINE.match(lines[index].rstrip("\r\n")):
                index += 1
            continue
        if any(META_LINE[key].match(line.rstrip("\r\n")) for key in META_KEYS):
            index += 1
            continue
        out.append(line)
        index += 1
    return "".join(out)


def source_list_lines(pages: list[dict[str, Any]], redmine_url: str) -> list[str]:
    lines = [SOURCE_LIST_ANCHOR]
    for page in pages:
        url = f"{redmine_url}/projects/{PROJECT}/wiki/{PAGE_URL_PATH[page['title']]}.json"
        lines.append(
            f"- `GET {url}`：页面 `{page['title']}`，快照来源 version `{page['version']}`，"
            f"`updated_on` 为 `{page['updated_on']}`。"
        )
    return lines


def candidate_text(base_text: str, pages: list[dict[str, Any]], meta: dict[str, str], redmine_url: str) -> str:
    """保留 base_text 的规则正文，只重写元数据行和来源页面清单。

    base_text 是当前 reference 或用户提供并审阅过的正文草稿。换行风格沿用
    base_text 首个换行的风格，不做归一化。
    """
    eol = "\r\n" if re.search(r"\r\n", base_text) else "\n"
    by_page = {page["title"]: page for page in pages}
    titles = list(by_page)

    def joined(field: str) -> str:
        if len(titles) == 1:
            return str(by_page[titles[0]][field])
        return "; ".join(f"{title}={by_page[title][field]}" for title in titles)

    meta_values = {
        "source_version": joined("version"),
        "source_updated_on": joined("updated_on"),
        "checked_at": meta["checked_at"],
        "checked_by": meta["checked_by"],
    }
    lines = base_text.splitlines(keepends=True)
    out: list[str] = []
    index = 0
    source_list_written = False
    while index < len(lines):
        line = lines[index]
        bare = line.rstrip("\r\n")
        replaced = False
        for key in META_KEYS:
            if META_LINE[key].match(bare):
                out.append(f"- `{key}: {meta_values[key]}`{eol}")
                replaced = True
                break
        if replaced:
            index += 1
            continue
        if bare == SOURCE_LIST_ANCHOR:
            index += 1
            while index < len(lines) and SOURCE_LIST_LINE.match(lines[index].rstrip("\r\n")):
                index += 1
            out.extend(text + eol for text in source_list_lines(pages, redmine_url))
            source_list_written = True
            continue
        out.append(line)
        index += 1
    if not source_list_written:
        out = _insert_source_list(out, source_list_lines(pages, redmine_url), eol)
    return "".join(out)


def _insert_source_list(lines: list[str], source_list: list[str], eol: str) -> list[str]:
    """base_text 还没有来源清单时，插到元数据 bullet 块之后。"""
    heading = next((i for i, line in enumerate(lines) if line.startswith("## 来源与快照元数据")), None)
    if heading is None:
        raise RefreshError(
            "bad_reference",
            "正文里找不到“## 来源与快照元数据”，无法定位元数据，拒绝改写。",
        )
    index = heading + 1
    while index < len(lines) and (lines[index].startswith("- ") or lines[index].startswith("  ")):
        index += 1
    block = [eol] if index > heading + 1 else []
    return lines[:index] + block + [text + eol for text in source_list] + [eol] + lines[index:]


# ---------------------------------------------------------------- 在线读取


def redmine_cli_path() -> Path:
    override = os.environ.get("REDMINE_CLI")
    return Path(override) if override else REPO_ROOT / "redmine" / "scripts" / "redmine.py"


def fetch_page(title: str, redmine_url: str) -> dict[str, Any]:
    """经 redmine CLI 读取一个 Wiki 页面，做 SKILL.md 要求的基本校验。

    与 redmine/scripts/redmine.py 的调用契约：子命令 ``get <已百分号编码的项目
    wiki 路径>``，实例地址来自环境变量 REDMINE_URL（与该 CLI 的默认值一致）；输出
    顶层 ``wiki_page`` 对象（该 CLI 的 ``ok/data`` 包装与裸 ``wiki_page`` 都接受）。
    """
    cli = redmine_cli_path()
    if not cli.is_file():
        raise RefreshError(
            "missing_dependency",
            f"找不到 Redmine CLI：{cli}。本执行器经它完成认证和 API 读取；可用 REDMINE_CLI 指定其他路径。",
        )
    encoded = PAGE_URL_PATH[title]
    command = [sys.executable, str(cli), "get", f"projects/{PROJECT}/wiki/{encoded}.json"]
    env = dict(os.environ, REDMINE_URL=redmine_url)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=180, env=env)
    except FileNotFoundError:
        raise RefreshError("missing_dependency", f"无法运行 {cli}。") from None
    except subprocess.TimeoutExpired:
        raise RefreshError("fetch_failed", f"读取页面「{title}」超时。") from None
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-300:]
        raise RefreshError("fetch_failed", f"读取页面「{title}」失败（退出码 {result.returncode}）：{detail}")
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        raise RefreshError("fetch_failed", f"页面「{title}」的响应不是 JSON。") from None
    wiki_page = None
    if isinstance(payload, dict):
        for container in (payload, payload.get("data") if isinstance(payload.get("data"), dict) else None):
            if isinstance(container, dict) and isinstance(container.get("wiki_page"), dict):
                wiki_page = container["wiki_page"]
                break
    if wiki_page is None or payload.get("ok") not in (None, True):
        detail = json.dumps(payload, ensure_ascii=False)[:300]
        raise RefreshError("fetch_failed", f"页面「{title}」读取未成功：{detail}")

    text = wiki_page.get("text")
    version = wiki_page.get("version")
    updated_on = wiki_page.get("updated_on")
    if not isinstance(text, str) or not text.strip():
        raise RefreshError("bad_page", f"页面「{title}」的 text 为空。")
    if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
        raise RefreshError("bad_page", f"页面「{title}」的 version 不是正整数：{version!r}。")
    if not isinstance(updated_on, str) or _parse_utc(updated_on) is None:
        raise RefreshError("bad_page", f"页面「{title}」的 updated_on 不可解析：{updated_on!r}。")
    return {"title": str(wiki_page.get("title") or title), "text": text, "version": version, "updated_on": updated_on}


# ---------------------------------------------------------------- 差异


def _line_diff(before: str, after: str) -> dict[str, Any]:
    import difflib

    changed = [
        line
        for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]
    return {
        "added": sum(1 for line in changed if line.startswith("+")),
        "removed": sum(1 for line in changed if line.startswith("-")),
    }


def diff_snapshot(before_text: str, after_text: str) -> dict[str, Any]:
    """规则正文与元数据分开比较：rules_changed 只由正文决定。"""
    body = _line_diff(strip_metadata(before_text), strip_metadata(after_text))
    meta_before = current_metadata(before_text)
    meta_after = current_metadata(after_text)
    return {
        "rules_changed": bool(body["added"] or body["removed"]),
        "body": body,
        "metadata_changed": meta_before != meta_after,
        "metadata_before": meta_before,
        "metadata_after": meta_after,
    }


# ---------------------------------------------------------------- plan


def _parse_body_drafts(values: list[str] | None) -> dict[str, Path]:
    drafts: dict[str, Path] = {}
    for item in values or []:
        name, separator, path = item.partition("=")
        if not separator or name not in SNAPSHOTS or not path:
            raise RefreshError(
                "usage",
                f"--body-draft 需要 <snapshot>=<路径> 形式且 snapshot 是 {sorted(SNAPSHOTS)}，得到：{item!r}",
            )
        drafts[name] = Path(path)
    return drafts


def gate_state_available() -> bool:
    """确认门禁状态目录可用（可创建、可写）。confirm_gate 工具依赖同一目录。"""
    directory = _load_gate().state_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".writable"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def cmd_plan(args: argparse.Namespace) -> dict[str, Any]:
    gate = _load_gate()
    drafts = _parse_body_drafts(args.body_draft)
    if not gate_state_available():
        raise RefreshError(
            "gate_unavailable",
            "确认门禁状态目录不可用（无法创建或写入）。写入授权依赖宿主的 confirm_gate 工具，它使用同一状态目录；"
            "先解决后再运行 plan（例如设置 CONFIRM_GATE_STATE_DIR）。",
        )
    with pending_lock():
        if PENDING_PATH.exists():
            raise RefreshError(
                "interrupted",
                "存在未完成的事务标记 .refresh.pending：上一次刷新可能中断。先运行 status 子命令按异常恢复处理，不要直接重跑。",
                pending=str(PENDING_PATH),
            )

        references: dict[str, str] = {}
        for snapshot in SNAPSHOTS:
            path = reference_path(snapshot)
            if not path.is_file():
                raise RefreshError("missing_reference", f"本地快照不存在：{path}。")
            references[snapshot] = read_raw(path)

        pages: dict[str, dict[str, Any]] = {}
        for title in PAGE_URL_PATH:
            pages[title] = fetch_page(title, args.redmine_url)

        # 来源版本变了，正文是人工摘录：必须先审阅在线全文并给出修订草稿。
        # 一次性收集全部缺草稿的快照，诊断里带上全部来源页面的在线全文。
        changed_sources: dict[str, dict[str, Any]] = {}
        missing_drafts: dict[str, dict[str, Any]] = {}
        for snapshot, config in SNAPSHOTS.items():
            local_versions = parse_source_versions(current_metadata(references[snapshot]).get("source_version"))
            changed = {}
            for title in config["pages"]:
                local = local_versions.get(title, local_versions.get("*"))
                if local != pages[title]["version"]:
                    changed[title] = {"local": local, "online": pages[title]["version"]}
            if changed:
                changed_sources[snapshot] = changed
                if snapshot not in drafts:
                    missing_drafts[snapshot] = changed
        if missing_drafts:
            online_pages = {
                title: {"version": page["version"], "updated_on": page["updated_on"], "text": page["text"]}
                for title, page in pages.items()
            }
            raise RefreshError(
                "sources_changed",
                "来源页面版本已变化，规则正文是人工摘录，不能只刷新元数据就声称规则已更新。"
                f"缺少审阅草稿的快照：{sorted(missing_drafts)}。先对照 online_pages 里的在线全文审阅，"
                "修订正文草稿后用 --body-draft <snapshot>=<path> 提供它，再重新 plan。",
                missing_drafts=missing_drafts,
                changed_sources=changed_sources,
                online_pages=online_pages,
            )

        checked_at = _utc_now_iso()
        temp_suffix = checked_at.replace("-", "").replace(":", "")

        # 先在内存里生成全部候选，随后按“标记 -> 临时文件”的顺序落盘。
        candidates: dict[str, str] = {}
        pending_snapshots: dict[str, Any] = {}
        for snapshot, config in SNAPSHOTS.items():
            base_text = read_raw(drafts[snapshot]) if snapshot in drafts else references[snapshot]
            snapshot_pages = [pages[title] for title in config["pages"]]
            candidate = candidate_text(base_text, snapshot_pages, {"checked_at": checked_at, "checked_by": args.checked_by}, args.redmine_url)
            ref_path = reference_path(snapshot)
            temp_name = f"{ref_path.name}.tmp-{temp_suffix}"
            candidates[snapshot] = candidate
            # sha256_before 绑定读取 reference 时的字节：fetch 期间发生的并发编辑
            # 不会混进本次候选，apply 的现场复核会把它们拦下来。
            pending_snapshots[snapshot] = {
                "reference": config["reference"],
                "sha256_before": hashlib.sha256(references[snapshot].encode("utf-8")).hexdigest(),
                "candidate_sha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest(),
                "temp": temp_name,
                "body_draft": str(drafts[snapshot]) if snapshot in drafts else None,
            }

        pending: dict[str, Any] = {
            "version": 1,
            "kind": KIND,
            "started_at": _utc_now_iso(),
            "checked_at": checked_at,
            "checked_by": args.checked_by,
            "pages": {title: {"version": page["version"], "updated_on": page["updated_on"]} for title, page in pages.items()},
            "snapshots": pending_snapshots,
        }
        # 事务标记先于任何候选临时文件、原子落盘。
        write_atomic(PENDING_PATH, json.dumps(pending, ensure_ascii=False, indent=2) + "\n")
        try:
            for snapshot, config in SNAPSHOTS.items():
                temp_path = reference_path(snapshot).with_name(pending_snapshots[snapshot]["temp"])
                write_atomic(temp_path, candidates[snapshot])
                if read_raw(temp_path) != candidates[snapshot]:
                    raise RefreshError("write_failed", f"候选文件写回校验不一致：{temp_path}")

            action = gate.create_action(
                KIND,
                {
                    "checked_at": checked_at,
                    "checked_by": args.checked_by,
                    "pages": pending["pages"],
                    "snapshots": {
                        snapshot: {
                            "reference": state["reference"],
                            "sha256_before": state["sha256_before"],
                            "candidate_sha256": state["candidate_sha256"],
                        }
                        for snapshot, state in pending_snapshots.items()
                    },
                },
                question="是否用本次读取到的两个候选快照替换本地规则快照？",
                summary=(
                    "刷新 BU1-SDK 规则快照：\n"
                    + "\n".join(
                        f"- {snapshot}：{config['reference']}（正文差异：{diff_snapshot(references[snapshot], candidates[snapshot])['rules_changed']}"
                        + ("，正文来自审阅草稿" if snapshot in drafts else "")
                        + "）"
                        for snapshot, config in SNAPSHOTS.items()
                    )
                ),
                approve_label="确认刷新规则",
                decline_label="保留现有快照",
            )
        except BaseException:
            for snapshot, state in pending_snapshots.items():
                remove_quietly(reference_path(snapshot).with_name(state["temp"]))
            remove_quietly(PENDING_PATH)
            raise

    report_snapshots = {
        snapshot: dict(
            reference=str(reference_path(snapshot)),
            body_draft=str(drafts[snapshot]) if snapshot in drafts else None,
            diff=diff_snapshot(references[snapshot], candidates[snapshot]),
        )
        for snapshot in SNAPSHOTS
    }
    return {
        "ok": True,
        "command": "plan",
        "action_id": action["id"],
        "approve_label": "确认刷新规则",
        "decline_label": "保留现有快照",
        "checked_at": checked_at,
        "checked_by": args.checked_by,
        "changed_sources": changed_sources or None,
        "pages": {
            title: {
                "version": page["version"],
                "updated_on": page["updated_on"],
                # 在线全文供审阅：正文是人工摘录，比对以此为准。
                "text": page["text"],
            }
            for title, page in pages.items()
        },
        "snapshots": report_snapshots,
        "pending": str(PENDING_PATH),
        "next": (
            "差异见 snapshots[].diff（正文与元数据分开），在线全文见 pages[].text。调用宿主 confirm_gate 工具（参数 "
            f'{{"action_id": "{action["id"]}"}}）让用户确认；仅当返回 approved 才运行 apply，其余结果一律停止并报告，'
            "用户拒绝或放弃时运行 abort。"
        ),
    }


# ---------------------------------------------------------------- apply / abort / status


def _live_state(pending: dict[str, Any]) -> dict[str, Any]:
    """从磁盘现场重新计算 authorize() 用的 payload。"""
    live_snapshots: dict[str, Any] = {}
    for snapshot, state in pending["snapshots"].items():
        ref_path = reference_path(snapshot)
        temp_path = ref_path.with_name(state["temp"])
        if not ref_path.is_file() or not temp_path.is_file():
            raise RefreshError(
                "changed_state",
                f"现场文件缺失：{ref_path if not ref_path.is_file() else temp_path}。事务保留，先用 status 判断处置方式。",
                snapshot=snapshot,
            )
        live_snapshots[snapshot] = {
            "reference": state["reference"],
            "sha256_before": sha256_bytes(ref_path),
            "candidate_sha256": sha256_bytes(temp_path),
        }
    return {
        "checked_at": pending.get("checked_at", ""),
        "checked_by": pending.get("checked_by", ""),
        "pages": pending.get("pages", {}),
        "snapshots": live_snapshots,
    }


def cmd_apply(args: argparse.Namespace) -> dict[str, Any]:
    gate = _load_gate()
    with pending_lock():
        if not PENDING_PATH.exists():
            raise RefreshError("no_transaction", "没有事务标记 .refresh.pending：先运行 plan。")
        pending = load_pending()
        missing = _pending_complete(pending)
        if missing:
            raise RefreshError(
                "incomplete_transaction",
                f"事务标记缺少 {missing}：plan 在写入候选前被中断，reference 未被替换。运行 abort 清理后重新 plan。",
            )
        try:
            gate.authorize(args.action_id, KIND, _live_state(pending))
        except gate.GateError as error:
            raise RefreshError(
                f"gate_{error.code}",
                f"确认门禁未放行：{error.message}",
                gate_code=error.code,
                changed=error.changed,
            ) from None

        replaced: list[str] = []
        try:
            for snapshot in SNAPSHOTS:
                state = pending["snapshots"][snapshot]
                ref_path = reference_path(snapshot)
                temp_path = ref_path.with_name(state["temp"])
                if sha256_bytes(ref_path) != state["sha256_before"]:
                    raise RefreshError(
                        "changed_state",
                        f"替换前发现 {ref_path} 与登记时的替换前哈希不一致，停止替换。事务保留，按异常恢复一节处理。",
                        snapshot=snapshot,
                    )
                if sha256_bytes(temp_path) != state["candidate_sha256"]:
                    raise RefreshError("verify_failed", f"替换前候选校验失败：{temp_path}", snapshot=snapshot)
                os.replace(temp_path, ref_path)
                replaced.append(snapshot)
                if sha256_bytes(ref_path) != state["candidate_sha256"]:
                    raise RefreshError("verify_failed", f"替换后复核失败：{ref_path}", snapshot=snapshot)
        except BaseException as error:
            if replaced:
                # 半更新是可见、可判定的状态：原子补记，绝不丢弃标记。
                write_atomic(PENDING_PATH, json.dumps(dict(pending, replaced=sorted(replaced)), ensure_ascii=False, indent=2) + "\n")
            if isinstance(error, RefreshError):
                raise
            raise RefreshError("replace_failed", f"替换中断：{error}", replaced=sorted(replaced)) from None

        # 全部替换成功后才清理；清理失败如实报告，不假装完成。
        cleanup_failures: list[str] = []
        for snapshot, state in pending["snapshots"].items():
            temp_path = reference_path(snapshot).with_name(state["temp"])
            if temp_path.exists() and not remove_checked(temp_path):
                cleanup_failures.append(str(temp_path))
        pending_removed = remove_checked(PENDING_PATH)
        if not pending_removed:
            cleanup_failures.append(str(PENDING_PATH))

    result: dict[str, Any] = {
        "ok": True,
        "command": "apply",
        "action_id": args.action_id,
        "replaced": replaced,
        "pages": pending.get("pages", {}),
        "checked_at": pending.get("checked_at"),
        "checked_by": pending.get("checked_by"),
        "pending": None if pending_removed else str(PENDING_PATH),
        "cleanup_failures": cleanup_failures or None,
    }
    if cleanup_failures:
        result["warning"] = "刷新已写入但事务清理未完成：" + "、".join(cleanup_failures) + "。完成清理后再重新调用本 skill。"
    return result


def cmd_abort(args: argparse.Namespace) -> dict[str, Any]:
    with pending_lock():
        if not PENDING_PATH.exists():
            return {"ok": True, "command": "abort", "pending": None, "note": "没有事务标记，无需清理。"}
        pending = load_pending()
        # 只有现场哈希证明两个 reference 都保持替换前原样，才允许清理事务。
        for snapshot, state in pending["snapshots"].items():
            ref_path = reference_path(snapshot)
            current = sha256_bytes(ref_path) if ref_path.is_file() else None
            if current == state.get("candidate_sha256"):
                raise RefreshError(
                    "already_replaced",
                    f"{snapshot} 的 reference 已被替换成候选内容。abort 不会清理事务：先运行 status，按 SKILL.md 异常恢复一节"
                    "用 git diff 判断回滚或保留，处置完成后手动删除标记和残留临时文件。",
                    snapshot=snapshot,
                )
            if current != state.get("sha256_before"):
                raise RefreshError(
                    "not_clean",
                    f"{snapshot} 的 reference 与事务记录的替换前哈希不一致（可能已部分替换或被外部修改）。abort 不清理事务："
                    "先运行 status 并按 SKILL.md 异常恢复一节处理。",
                    snapshot=snapshot,
                )
        removed: list[str] = []
        cleanup_failures: list[str] = []
        for snapshot, state in pending["snapshots"].items():
            temp_path = reference_path(snapshot).with_name(state["temp"])
            if temp_path.exists() and not remove_checked(temp_path):
                cleanup_failures.append(str(temp_path))
            elif temp_path.exists():
                removed.append(str(temp_path))
        if not remove_checked(PENDING_PATH):
            cleanup_failures.append(str(PENDING_PATH))
    result: dict[str, Any] = {
        "ok": True,
        "command": "abort",
        "removed_temp_files": removed,
        "pending": None if not PENDING_PATH.exists() else str(PENDING_PATH),
        "cleanup_failures": cleanup_failures or None,
        "note": "已删除临时文件和事务标记，reference 保持不变。",
    }
    if cleanup_failures:
        result["warning"] = "中止已生效但清理未完成：" + "、".join(cleanup_failures)
    return result


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    if not PENDING_PATH.exists():
        return {
            "ok": True,
            "command": "status",
            "pending": None,
            "snapshots": {
                snapshot: {"reference": str(reference_path(snapshot)), "exists": reference_path(snapshot).is_file()}
                for snapshot in SNAPSHOTS
            },
        }
    pending = load_pending()
    missing = _pending_complete(pending)
    snapshots: dict[str, Any] = {}
    for snapshot, state in pending["snapshots"].items():
        ref_path = reference_path(snapshot)
        temp_path = ref_path.with_name(state["temp"])
        current = sha256_bytes(ref_path) if ref_path.is_file() else None
        snapshots[snapshot] = {
            "reference": str(ref_path),
            "sha256_before": state.get("sha256_before"),
            "candidate_sha256": state.get("candidate_sha256"),
            "current_sha256": current,
            "already_replaced": current is not None and current == state.get("candidate_sha256"),
            "untouched": current is not None and current == state.get("sha256_before"),
            "temp_file_exists": temp_path.is_file(),
        }
    return {
        "ok": True,
        "command": "status",
        "pending": str(PENDING_PATH),
        "started_at": pending.get("started_at"),
        "incomplete": missing,
        "replaced_recorded": pending.get("replaced", []),
        "snapshots": snapshots,
        "note": (
            "存在中断的事务标记。按 SKILL.md 异常恢复一节处理：用 git diff 查看半更新状态，回滚或补完替换后删除标记和"
            "残留临时文件，再重新调用刷新。"
        ),
    }


# ---------------------------------------------------------------- 命令行


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BU1-SDK 规则快照刷新执行器")
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("plan", help="读取在线页面、生成候选并登记待确认动作")
    plan.add_argument("--redmine-url", default=os.environ.get("REDMINE_URL") or DEFAULT_REDMINE_URL)
    plan.add_argument("--checked-by", default=DEFAULT_CHECKED_BY)
    plan.add_argument(
        "--body-draft",
        action="append",
        metavar="SNAPSHOT=PATH",
        help="审阅后的正文草稿（完整 reference 内容）；来源版本变化时必须提供",
    )

    apply_cmd = commands.add_parser("apply", help="凭确认凭据原子替换两个 reference")
    apply_cmd.add_argument("--action-id", required=True)

    commands.add_parser("abort", help="丢弃本次刷新：仅在两个 reference 都未被替换时清理")
    commands.add_parser("status", help="报告事务标记与中断恢复所需的事实")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handler = {"plan": cmd_plan, "apply": cmd_apply, "abort": cmd_abort, "status": cmd_status}[args.command]
    try:
        result = handler(args)
    except RefreshError as error:
        _emit(dict({"ok": False, "error": error.code, "message": error.message}, **error.extra))
        return 1
    _emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
