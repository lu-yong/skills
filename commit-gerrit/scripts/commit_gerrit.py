#!/usr/bin/env python3
"""commit-gerrit 执行器：暂存、提交、推送三个写操作都过确认门禁。

用法（业务流程见 ../SKILL.md）：

  commit_gerrit.py preflight
  commit_gerrit.py stage --plan --issue ID --message-file F [--mode new|amend] [--scope PATH ...]
  commit_gerrit.py stage --action ID
  commit_gerrit.py commit-plan --mode new|amend --stage-action ID
  commit_gerrit.py commit --action ID
  commit_gerrit.py push-plan --commit-action ID --sha SHA
  commit_gerrit.py push --action ID

plan 子命令只读本地仓库（外加 stage --plan 的一次 Redmine 问题读取和一次
ls-remote 目标探测）并登记待确认动作；执行子命令在写之前用现场重算的 payload
换取门禁放行（confirm-gate/scripts/gate.py），登记后现场有任何漂移都会被拒绝。

成功执行会向门禁状态目录写回执（stage/commit 各一张），下一步的 plan 子命令
核验回执后才登记动作：commit-plan 核验 stage 回执，push-plan 核验 commit 回执。
回执与确认凭据同一信任边界：都在仓库之外，模型无法伪造。

Gerrit 实例与推送主机登记复用 gerrit/scripts/gerrit.py 与其 instances.json，
Redmine 读取复用 redmine/scripts/redmine.py，均只读。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_FILE = REPO_ROOT / "commit-gerrit" / "references" / "bu1-sdk-gerrit-rules.md"
KIND_STAGE = "commit_gerrit.stage"
KIND_COMMIT = "commit_gerrit.commit"
KIND_PUSH = "commit_gerrit.push"
BASE_BRANCHES = {"main", "master", "develop", "sdk-release"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SUBJECT_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|test|chore):\s*(\[[1-9][0-9]*\]|[1-9][0-9]*)\s*:\s*(.+)$"
)
TRAILER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*:\s.")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


class ExecError(Exception):
    """执行器拒绝继续。code 给流程分支，message 给人和模型看。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _load("skill_confirm_gate_gate", REPO_ROOT / "confirm-gate" / "scripts" / "gate.py")
gerrit = _load("skill_gerrit_gerrit", REPO_ROOT / "gerrit" / "scripts" / "gerrit.py")
redmine = _load("skill_redmine_redmine", REPO_ROOT / "redmine" / "scripts" / "redmine.py")


# ---------------------------------------------------------------- git 基础


def _git(*args: str, check: bool = True, cwd: Path | str | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=cwd or repo_root(), capture_output=True)
    if check and result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise ExecError("git", f"git {' '.join(args[:3])} … 失败：{detail}")
    return result


def _git_text(*args: str, cwd: Path | str | None = None) -> str:
    return _git(*args, cwd=cwd).stdout.decode("utf-8", "replace")


def repo_root() -> Path:
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True)
    if result.returncode != 0:
        raise ExecError("not_a_repository", "当前目录不在 Git 仓库里。请切到相关仓库后重试。")
    return Path(result.stdout.decode("utf-8", "replace").strip())


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_digest(path: Path) -> str:
    """文件 SHA-256；读不到就拒绝，不返回 None（None 会被当作“无需比对”放过漂移）。"""
    try:
        return _sha256(path.read_bytes())
    except OSError as error:
        raise ExecError(
            "rules_unreadable",
            f"读不到本地规则快照 {path}：{error}。规则不可用时不能登记或提交。",
        ) from error


def _unique_config(key: str, root: Path, missing_code: str, ambiguous_code: str, what: str) -> str:
    """一个配置键必须恰好一个值；缺失或多值都拒绝，不取第一个。"""
    result = _git("config", "--get-all", key, check=False, cwd=root)
    values = [line for line in result.stdout.decode("utf-8", "replace").splitlines() if line.strip()]
    if not values:
        raise ExecError(missing_code, f"没有配置 {key}（{what}）。请先配置后重试。")
    if len(values) > 1:
        raise ExecError(ambiguous_code, f"{key} 配置了 {len(values)} 个值，无法唯一确定{what}。")
    return values[0]


def _hook_path(root: Path) -> Path:
    """Git 解析出的 commit-msg hook；相对路径按仓库根归一。"""
    raw = _git_text("rev-parse", "--git-path", "hooks/commit-msg", cwd=root).strip()
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _effective_push_url(remote: str, root: Path) -> str:
    """remote 实际生效的推送 URL；不唯一就拒绝。"""
    result = _git("remote", "get-url", "--push", "--all", remote, check=False, cwd=root)
    candidates = [line.strip() for line in result.stdout.decode("utf-8", "replace").splitlines() if line.strip()]
    if len(candidates) != 1:
        raise ExecError(
            "no_unique_push_url", f"remote {remote} 的推送 URL 不唯一（{len(candidates)} 个），无法确定推送目标。"
        )
    return candidates[0]


# ---------------------------------------------------------------- 阶段零：本地硬检查与目标探测


def phase0_local(root: Path) -> dict[str, Any]:
    """阶段零本地硬检查：分支、目标分支、remote、push URL 与 hook。不发网络请求。"""
    branch = _git_text("branch", "--show-current", cwd=root).strip()
    if not branch:
        raise ExecError("detached_head", "当前处于 detached HEAD，请先创建并切换本地工作分支。")
    if branch in BASE_BRANCHES:
        raise ExecError("base_branch", f"分支 {branch} 是基础分支，请先创建并切换 topic/work 分支。")
    merge = _unique_config(
        f"branch.{branch}.merge", root, "no_target_branch", "ambiguous_target_branch", "Gerrit 目标分支"
    )
    if _git("check-ref-format", merge, check=False, cwd=root).returncode != 0:
        raise ExecError(
            "bad_merge_ref",
            f"branch.{branch}.merge 的值 {merge!r} 不是合法的引用名，拒绝据此确定目标分支。",
        )
    dest_branch = merge[len("refs/heads/") :] if merge.startswith("refs/heads/") else merge
    if branch == dest_branch:
        raise ExecError("same_as_target", f"本地分支 {branch} 与目标分支同名，不是独立工作分支。")
    remote_name = _unique_config(
        f"branch.{branch}.remote", root, "no_remote", "ambiguous_remote", "推送 remote"
    )
    push_url = _effective_push_url(remote_name, root)
    parsed = gerrit.parse_remote(push_url)
    host = parsed["host"]
    if host not in gerrit.push_hosts():
        raise ExecError(
            "host_not_allowed",
            f"推送目标 {gerrit.redact_url(push_url)} 不是 Gerrit 实例登记（gerrit/instances.json）允许的公司 Gerrit 主机。",
        )
    hook = _hook_path(root)
    if not hook.is_file() or not os.access(hook, os.X_OK):
        raise ExecError("hook_missing", f"缺少可执行的 commit-msg hook：{hook}。")
    return {
        "branch": branch,
        "merge": merge,
        "dest_branch": dest_branch,
        "remote": remote_name,
        "push_url": push_url,
        "host": host,
        "hook_path": str(hook),
    }


def check_remote_target(push_url: str, dest_branch: str, root: Path) -> None:
    """唯一的网络探测点：确认目标分支在推送目标上存在。只在 stage --plan 里调用。"""
    probe = _git("ls-remote", "--exit-code", "--heads", push_url, f"refs/heads/{dest_branch}", check=False, cwd=root)
    if probe.returncode != 0:
        raise ExecError(
            "target_branch_unreachable",
            f"目标分支 refs/heads/{dest_branch} 在推送目标上不存在或无法访问。",
        )


# ---------------------------------------------------------------- 工作区快照与范围


def make_scope(paths: list[str] | None) -> dict[str, Any]:
    if not paths:
        return {"mode": "default", "paths": []}
    normalized = sorted({os.path.normpath(path).replace(os.sep, "/") for path in paths})
    return {"mode": "paths", "paths": normalized}


def _scope_pathspecs(scope: dict[str, Any]) -> list[str] | None:
    return None if scope["mode"] == "default" else [":(literal)" + path for path in scope["paths"]]


def staged_paths(root: Path) -> list[str]:
    """已暂存路径；--no-renames 让改名的源和目标都各自列出，两侧都被绑定。"""
    stdout = _git("diff", "--cached", "--name-only", "--no-renames", "-z", cwd=root).stdout
    return sorted(raw.decode("utf-8", "replace") for raw in stdout.split(b"\0") if raw)


def index_fingerprint(root: Path) -> str:
    """完整索引指纹：ls-files --stage（模式/对象/阶段/路径）。

    不用 diff 输出：diff 会受 rename 检测、submodule 忽略等配置影响，漏掉真差异。
    """
    return _sha256(_git("ls-files", "--stage", "-z", cwd=root).stdout)


def snapshot(root: Path, scope: dict[str, Any]) -> dict[str, Any]:
    """按确认范围计算固定字段快照：只记录路径、类型、大小和哈希，不记录内容。

    暂存哈希永远覆盖完整索引（提交取整个索引）；工作区哈希按确认范围过滤。
    根目录与规则快照摘要绑定仓库身份和规则版本。
    """
    pathspecs = _scope_pathspecs(scope)
    head = _git_text("rev-parse", "HEAD", cwd=root).strip()
    if not SHA_RE.fullmatch(head):
        raise ExecError("unborn_head", "当前分支还没有提交（unborn HEAD）。")

    worktree_args = ["diff", "--binary", "HEAD"]
    if pathspecs:
        worktree_args += ["--", *pathspecs]
    untracked_args = ["ls-files", "--others", "--exclude-standard", "-z"]
    if pathspecs:
        untracked_args += ["--", *pathspecs]
    untracked: list[dict[str, Any]] = []
    for raw in _git(*untracked_args, cwd=root).stdout.split(b"\0"):
        if not raw:
            continue
        path = raw.decode("utf-8", "replace")
        target = root / path
        is_link = target.is_symlink()
        content = os.readlink(target).encode("utf-8") if is_link else target.read_bytes()
        untracked.append(
            {"path": path, "type": "symlink" if is_link else "file", "size": len(content), "sha256": _sha256(content)}
        )
    untracked.sort(key=lambda item: item["path"])
    listing = "".join(f"{i['path']}|{i['type']}|{i['size']}|{i['sha256']}\n" for i in untracked)

    hook = _hook_path(root)
    hook_sha = _sha256(hook.read_bytes()) if hook.is_file() else None
    confirmed = phase0_local(root)
    return {
        "root": str(root),
        "head": head,
        "worktree_hash": _sha256(_git(*worktree_args, cwd=root).stdout),
        "staged_hash": index_fingerprint(root),
        "staged_paths": staged_paths(root),
        "untracked": untracked,
        "untracked_hash": _sha256(listing.encode("utf-8")),
        "branch": confirmed["branch"],
        "merge": confirmed["merge"],
        "remote": confirmed["remote"],
        "push_url": confirmed["push_url"],
        "host": confirmed["host"],
        "dest_branch": confirmed["dest_branch"],
        "hook_path": str(hook),
        "hook_sha": hook_sha,
        "rules_sha256": _file_digest(RULES_FILE),
    }


# ---------------------------------------------------------------- 回执


def _receipt_path(kind: str, action_id: str) -> Path:
    return gate.state_dir() / "receipts" / f"{kind}.{action_id}.json"


def _write_receipt(kind: str, action_id: str, data: dict[str, Any]) -> None:
    path = _receipt_path(kind, action_id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def _read_receipt(kind: str, action_id: str) -> dict[str, Any]:
    if not re.match(r"^[0-9a-f]{12}$", str(action_id or "")):
        raise ExecError("bad_receipt", f"动作编号格式不对：{action_id!r}。")
    path = _receipt_path(kind, action_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ExecError(
            "no_receipt",
            f"找不到 {kind} 动作 {action_id} 的成功回执。只有成功执行过的动作才有回执；请先完成上一步的执行。",
        ) from None
    if not isinstance(data, dict):
        raise ExecError("bad_receipt", f"{path} 的内容不是对象。")
    return data


# ---------------------------------------------------------------- Redmine 读取


def read_issue(issue: str) -> dict[str, Any]:
    """经共享 redmine.py 读取问题详情，映射成流程要记录的字段。"""
    data, _meta = redmine.get_issue(issue, include=[])
    project = data.get("project") or {}
    tracker = data.get("tracker") or {}
    status = data.get("status") or {}
    return {
        "id": str(data.get("id")),
        "subject": data.get("subject"),
        "project": project.get("identifier"),
        "tracker": tracker.get("name"),
        "status": status.get("name"),
    }


# ---------------------------------------------------------------- 消息格式


def lint_message(text: str, issue_id: str | None = None) -> list[str]:
    """按规则快照校验完整提交消息；方括号两种写法都接受（快照未定字面量）。"""
    issues: list[str] = []
    lines = text.rstrip("\n").splitlines()
    if not lines or not lines[0].strip():
        return ["消息为空。"]
    match = SUBJECT_RE.match(lines[0].strip())
    if not match:
        issues.append(
            "首行不符合 Type: [Redmine ID]: [Subject] 结构（Type 枚举 feat/fix/docs/style/refactor/test/chore）："
            f"{lines[0]!r}"
        )
    else:
        header_id, subject = match.group(2), match.group(3).strip()
        if header_id.startswith("["):
            header_id = header_id[1:-1]
        if subject.startswith("[") and subject.endswith("]"):
            subject = subject[1:-1]
        if issue_id is not None and header_id != str(issue_id):
            issues.append(f"标题里的问题号 {header_id} 与已验证的 Redmine 问题号 {issue_id} 不一致。")
        if len(subject) > 50:
            issues.append(f"Subject 超过 50 个字符（{len(subject)}）：{subject}")
        if not subject or not CJK_RE.match(subject[0]):
            issues.append(f"Subject 必须以中文动词开头：{subject!r}。")
        if subject.endswith("。") or subject.endswith("."):
            issues.append(f"Subject 结尾不能加句号：{subject!r}。")
    if len(lines) > 1 and lines[1].strip():
        issues.append("Subject 与正文之间必须空一行。")
    if any(line.lstrip().startswith("Change-Id:") for line in lines[1:]):
        issues.append("新提交的 Change-Id 由 commit-msg hook 添加，请从草稿中移除。")
    for index, line in enumerate(lines[1:], start=2):
        if len(line) > 72:
            issues.append(f"第 {index} 行超过 72 个字符（{len(line)}）。")
    return issues


def lint_paragraph(paragraph: str) -> list[str]:
    """amend 追加段只查行宽与非空；保留的部分不重新校验。"""
    if not paragraph.strip():
        return ["追加段落为空。"]
    if any(line.lstrip().startswith("Change-Id:") for line in paragraph.splitlines()):
        return ["amend 追加段不得包含 Change-Id；原评审标识会被保留。"]
    return [
        f"追加段落有行超过 72 个字符（{len(line)}）。"
        for line in paragraph.rstrip("\n").splitlines()
        if len(line) > 72
    ]


def synthesize_amend(head_message: str, paragraph: str) -> str:
    """保留 HEAD 的 Subject/Body/Footer，把事实段插入 Footer 之前；无 Footer 则追加结尾。"""
    message = head_message.rstrip("\n")
    paragraph = paragraph.strip("\n")
    separators = list(re.finditer(r"\n(?:[ \t]*\n)+", message))
    if separators:
        separator = separators[-1]
        footer_lines = message[separator.end():].splitlines()
        if footer_lines and TRAILER_RE.match(footer_lines[0]) and all(
            TRAILER_RE.match(line) or line.startswith((" ", "\t")) for line in footer_lines
        ):
            return f"{message[:separator.start()]}\n\n{paragraph}{message[separator.start():]}\n"
    if gerrit.change_id_of(head_message) is not None:
        raise ExecError("amend_footer_ambiguous", "无法确定现有提交的 Footer 边界。请先核对提交消息。")
    return f"{message}\n\n{paragraph}\n"


def _strip_change_id(message: str) -> str:
    """去掉 hook 可能补上的 Change-Id 行，用于「消息只多了 Change-Id」的比对。"""
    kept = [line for line in message.splitlines() if not line.strip().startswith("Change-Id:")]
    text = "\n".join(kept).strip("\n")
    return re.sub(r"\n{3,}", "\n\n", text)


def _read_message_file(path: str) -> str:
    file = Path(path)
    if not file.is_file():
        raise ExecError("message_file_unreadable", f"读不到消息文件 {path}。")
    text = file.read_text(encoding="utf-8")
    if not text.strip():
        raise ExecError("message_file_unreadable", f"消息文件 {path} 为空。")
    return text


# ---------------------------------------------------------------- stage：登记与执行


def _issue_line(issue: dict[str, Any]) -> str:
    bits = [f"#{issue.get('id')}"]
    for key, label in (("project", "项目"), ("tracker", "跟踪"), ("status", "状态")):
        if issue.get(key):
            bits.append(f"{label} {issue[key]}")
    if issue.get("subject"):
        bits.append(f"「{issue['subject']}」")
    return "，".join(bits)


def _redacted(value: Any) -> Any:
    """输出前去掉 URL 里的内嵌凭据。payload 本身保持原值参与摘要比对。"""
    if isinstance(value, dict):
        return {key: _redacted(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redacted(item) for item in value]
    if isinstance(value, str):
        return gerrit.redact_url(value)
    return value


def _destination(snap: dict[str, Any]) -> dict[str, Any]:
    return {
        "branch": snap["branch"],
        "merge": snap["merge"],
        "dest_branch": snap["dest_branch"],
        "remote": snap["remote"],
        "push_url": snap["push_url"],
        "host": snap["host"],
    }


def plan_stage(args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root()
    confirmed = phase0_local(root)
    check_remote_target(confirmed["push_url"], confirmed["dest_branch"], root)
    issue = read_issue(args.issue)
    scope = make_scope(args.scope)
    message = _read_message_file(args.message_file)
    problems = lint_message(message, issue["id"]) if args.mode == "new" else lint_paragraph(message)
    if problems:
        raise ExecError("message_lint", "提交消息不符合规则：" + "；".join(problems))
    if scope["mode"] == "paths":
        outside = [path for path in staged_paths(root) if path not in set(scope["paths"])]
        if outside:
            raise ExecError(
                "staged_out_of_scope",
                "暂存区里已有确认范围之外的路径：" + "、".join(outside)
                + "。先询问用户是否扩展提交范围，或让用户自行处理暂存区。",
            )
    snap = snapshot(root, scope)
    scope_text = "整个工作区（默认范围）" if scope["mode"] == "default" else "、".join(scope["paths"])
    preserved = "、".join(snap["staged_paths"]) or "无"
    summary = (
        "commit-gerrit：暂存并创建 Gerrit 评审补丁\n"
        f"Redmine {_issue_line(issue)}\n"
        f"分支 {snap['branch']} → {snap['dest_branch']}（remote {snap['remote']}，"
        f"host {snap['host'] or '本地'}）\n"
        f"提交范围：{scope_text}｜已有暂存版本（保留不动）：{preserved}\n"
        f"HEAD {snap['head'][:12]}｜工作区 {snap['worktree_hash'][:12]}｜暂存 {snap['staged_hash'][:12]}"
        f"｜未跟踪 {len(snap['untracked'])} 个｜hook {snap['hook_sha'][:12] if snap['hook_sha'] else '缺失'}\n"
        f"完整消息：\n{message.rstrip()}"
    )
    action = gate.create_action(
        KIND_STAGE,
        {"scope": scope, "issue": issue, "message": message, "mode": args.mode, "snapshot": snap},
        question="是否按以上草稿和固定快照暂存确认范围内的全部修改？",
        summary=summary,
        approve_label="确认提交",
    )
    return {
        "action_id": action["id"],
        "kind": KIND_STAGE,
        "question": action["question"],
        "summary": summary,
        "approve_label": action["approve_label"],
        "decline_label": action["decline_label"],
        "scope": scope,
        "issue": issue,
        "message": message,
        "snapshot": _redacted(snap),
        "note": "展示完整草稿后，请用户经宿主 confirm_gate 确认，再运行 stage --action。",
    }


def run_stage(args: argparse.Namespace) -> dict[str, Any]:
    action = gate.load_action(args.action, KIND_STAGE)
    payload = action["payload"]
    root = repo_root()
    live_payload = dict(payload, snapshot=snapshot(root, payload["scope"]))
    gate.authorize(args.action, KIND_STAGE, live_payload)
    scope = payload["scope"]
    preserve = set(payload["snapshot"]["staged_paths"])  # 已有暂存版本的路径不再 git add，原样保留
    if scope["mode"] == "default":
        # 排除项必须用 literal：文件名里可能含通配符字符。
        add_pathspecs = ["."] + [":(exclude,literal)" + path for path in sorted(preserve)]
    else:
        add_pathspecs = [":(literal)" + path for path in scope["paths"] if path not in preserve]
    if add_pathspecs:
        # 空列表絶不能进入 git add -A --：那会暂存全部内容。
        _git(*(["add", "-A", "--", *add_pathspecs]), cwd=root)
    now_staged = staged_paths(root)
    if scope["mode"] == "paths":
        beyond = [path for path in now_staged if path not in set(scope["paths"])]
        if beyond:
            raise ExecError("staged_beyond_scope", "暂存后出现范围外路径：" + "、".join(beyond) + "。停止，不提交。")
    check = _git("diff", "--cached", "--check", cwd=root, check=False)
    if check.returncode != 0:
        raise ExecError(
            "staged_check_failed",
            "git diff --cached --check 未通过：" + check.stderr.decode("utf-8", "replace").strip(),
        )
    staged_hash = index_fingerprint(root)
    receipt = {
        "kind": KIND_STAGE,
        "action_id": args.action,
        "root": str(root),
        "scope": scope,
        "issue": payload["issue"],
        "message": payload["message"],
        "mode": payload["mode"],
        "destination": _destination(payload["snapshot"]),
        "staged_paths": now_staged,
        "staged_hash": staged_hash,
        "preserved_paths": sorted(preserve),
        "head": payload["snapshot"]["head"],
        "hook_sha": payload["snapshot"]["hook_sha"],
        "rules_sha256": payload["snapshot"]["rules_sha256"],
    }
    _write_receipt("stage", args.action, receipt)
    gate.discard_action(args.action)
    return {
        "staged_paths": now_staged,
        "preserved_paths": sorted(preserve),
        "staged_hash": staged_hash,
        "stat": _git_text("diff", "--cached", "--stat", cwd=root).strip(),
        "scope": scope,
        "message": payload["message"],
        "mode": payload["mode"],
        "destination": _redacted(_destination(payload["snapshot"])),
    }


# ---------------------------------------------------------------- commit：登记与执行


def _commit_state(root: Path) -> dict[str, Any]:
    branch = _git_text("branch", "--show-current", cwd=root).strip()
    if not branch:
        raise ExecError("detached_head", "当前处于 detached HEAD。")
    confirmed = phase0_local(root)
    hook = _hook_path(root)
    return {
        "root": str(root),
        "head": _git_text("rev-parse", "HEAD", cwd=root).strip(),
        "staged_hash": index_fingerprint(root),
        "staged_paths": staged_paths(root),
        "tree": _git_text("write-tree", cwd=root).strip(),
        "branch": branch,
        "merge": confirmed["merge"],
        "remote": confirmed["remote"],
        "push_url": confirmed["push_url"],
        "host": confirmed["host"],
        "dest_branch": confirmed["dest_branch"],
        "hook_path": str(hook),
        "hook_sha": _sha256(hook.read_bytes()),
        "rules_sha256": _file_digest(RULES_FILE),
    }


def run_preflight(args: argparse.Namespace) -> dict[str, Any]:
    """阶段零只读预检：本地硬检查 + 唯一网络探测点，供 Redmine 读取/起草前调用。"""
    root = repo_root()
    confirmed = phase0_local(root)
    check_remote_target(confirmed["push_url"], confirmed["dest_branch"], root)
    return {
        "phase0": "ok",
        "destination": _redacted(confirmed),
        "note": "硬检查与目标分支探测通过。后续 stage --plan 会自行复核现场与目标。",
    }


def _verify_stage_receipt(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    receipt = _read_receipt("stage", args.stage_action)
    if receipt.get("root") != str(root):
        raise ExecError(
            "receipt_root_mismatch",
            f"stage 回执属于仓库 {receipt.get('root')}，当前仓库是 {root}。请在对应仓库里执行。",
        )
    state = _commit_state(root)
    if state["staged_hash"] != receipt.get("staged_hash"):
        raise ExecError(
            "index_changed_since_stage",
            "暂存区在 stage 执行后又发生了变化，与 stage 回执不一致。请重新走 stage 流程。",
        )
    if state["head"] != receipt.get("head"):
        raise ExecError(
            "head_changed_since_stage",
            "HEAD 在 stage 执行后发生了变化，与 stage 回执不一致。请重新走 stage 流程。",
        )
    if state["hook_sha"] != receipt.get("hook_sha"):
        raise ExecError(
            "hook_changed_since_stage",
            "commit-msg hook 在 stage 执行后发生了变化，与 stage 回执不一致。请重新走 stage 流程。",
        )
    if state["rules_sha256"] != receipt.get("rules_sha256"):
        raise ExecError(
            "rules_changed_since_stage",
            "本地规则快照在 stage 执行后发生了变化。请重新走 stage 流程。",
        )
    if _destination(state) != receipt.get("destination"):
        raise ExecError(
            "destination_changed_since_stage",
            "推送目标（分支/remote/URL/目标分支）在 stage 之后发生了变化。请重新走 stage 流程。",
        )
    if args.mode != receipt.get("mode"):
        raise ExecError(
            "mode_mismatch",
            f"stage 登记的提交方式是 {receipt.get('mode')!r}，现在是 {args.mode!r}。请按 stage 确认的方式执行。",
        )
    receipt["live_state"] = state
    return receipt


def plan_commit(args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root()
    receipt = _verify_stage_receipt(args, root)
    state = receipt["live_state"]
    if not state["staged_paths"]:
        raise ExecError("nothing_staged", "暂存区为空，没有可提交的内容。")
    if args.mode == "new":
        message = receipt["message"].rstrip("\n") + "\n"
        problems = lint_message(message, receipt["issue"]["id"])
        approve_label = "创建新提交"
        question = "是否用已展示的完整消息对当前暂存内容创建新提交？"
        mode_note = "新提交使用 stage 已确认的完整 commit message。"
    else:
        head_message = _git_text("log", "-1", "--format=%B", state["head"], cwd=root)
        message = synthesize_amend(head_message, receipt["message"])
        problems = lint_paragraph(receipt["message"])
        approve_label = "amend 当前提交"
        question = "是否按已展示的合成消息改写当前最新提交（amend）？"
        mode_note = "保留当前提交的 Subject/Body/Footer，追加段插入 Footer 之前。"
    if problems:
        raise ExecError("message_lint", "提交消息不符合规则：" + "；".join(problems))
    scope_text = "整个工作区（默认范围）" if receipt["scope"]["mode"] == "default" else "、".join(receipt["scope"]["paths"])
    summary = (
        f"commit-gerrit：{'amend 当前提交' if args.mode == 'amend' else '创建新提交'}\n"
        f"{mode_note}\n"
        f"HEAD {state['head'][:12]}｜暂存 {len(state['staged_paths'])} 个文件"
        f"｜暂存哈希 {state['staged_hash'][:12]}｜树 {state['tree'][:12]}\n"
        f"提交范围：{scope_text}｜目标 {state['dest_branch']}（remote {receipt['destination']['remote']}）\n"
        f"完整消息：\n{message.rstrip()}"
    )
    action = gate.create_action(
        KIND_COMMIT,
        {
            "mode": args.mode,
            "message": message,
            "state": state,
            "scope": receipt["scope"],
            "destination": receipt["destination"],
            "stage_action_id": args.stage_action,
        },
        question=question,
        summary=summary,
        approve_label=approve_label,
    )
    return {
        "action_id": action["id"],
        "kind": KIND_COMMIT,
        "question": question,
        "summary": summary,
        "approve_label": approve_label,
        "decline_label": action["decline_label"],
        "mode": args.mode,
        "message": message,
        "staged_paths": state["staged_paths"],
        "scope": receipt["scope"],
        "destination": _redacted(receipt["destination"]),
    }


def run_commit(args: argparse.Namespace) -> dict[str, Any]:
    action = gate.load_action(args.action, KIND_COMMIT)
    payload = action["payload"]
    root = repo_root()
    live_state = _commit_state(root)
    # 规则漂移在 authorize 前就拦下（规则变了确认就失效，不消耗凭据）。
    if live_state["rules_sha256"] != payload["state"].get("rules_sha256"):
        raise ExecError(
            "rules_changed_since_plan",
            "本地规则快照在 commit 确认后发生了变化。动作作废，请重新走 stage 流程。",
        )
    gate.authorize(args.action, KIND_COMMIT, dict(payload, state=live_state))
    old_head = payload["state"]["head"]

    fd, temp = tempfile.mkstemp(prefix="commit-gerrit-msg-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload["message"])
        os.chmod(temp, 0o600)
        commit_args = ["commit", "--cleanup=verbatim", "-F", temp] + (["--amend"] if payload["mode"] == "amend" else [])
        result = subprocess.run(["git", *commit_args], cwd=root, capture_output=True, env=dict(os.environ, GIT_EDITOR="true"))
        if result.returncode != 0:
            raise ExecError(
                "commit_failed",
                "git commit 失败（暂存区已保留，未推送）：" + result.stderr.decode("utf-8", "replace").strip(),
            )
    finally:
        try:
            os.unlink(temp)
        except OSError:
            pass

    sha = _git_text("rev-parse", "HEAD", cwd=root).strip()
    final_message = _git_text("log", "-1", "--format=%B", sha, cwd=root)
    change_id = gerrit.change_id_of(final_message)
    if change_id is None:
        raise ExecError(
            "missing_change_id",
            f"提交 {sha[:12]} 的消息缺少唯一合法的 Change-Id（应由 commit-msg hook 生成）。不要推送这个提交。",
        )
    if payload["mode"] == "amend":
        original_change_id = gerrit.change_id_of(_git_text("log", "-1", "--format=%B", old_head, cwd=root))
        if original_change_id and change_id != original_change_id:
            raise ExecError(
                "change_id_rewritten",
                f"amend 后的 Change-Id {change_id} 与原提交的 {original_change_id} 不一致，评审身份被改写。不要推送这个提交。",
            )
    if _strip_change_id(final_message).strip() != _strip_change_id(payload["message"]).strip():
        raise ExecError(
            "message_rewritten",
            f"提交 {sha[:12]} 的最终消息与确认稿不一致（除 hook 补上的 Change-Id 外还有差异）。不要推送这个提交。",
        )
    realized_tree = _git_text("rev-parse", f"{sha}^{{tree}}", cwd=root).strip()
    if realized_tree != payload["state"]["tree"]:
        raise ExecError(
            "tree_mismatch",
            f"提交 {sha[:12]} 的结果树 {realized_tree[:12]} 与确认时的索引树 {payload['state']['tree'][:12]} 不一致。不要推送这个提交。",
        )
    parents = _git_text("log", "-1", "--format=%P", sha, cwd=root).split()
    old_parents = _git_text("log", "-1", "--format=%P", old_head, cwd=root).split()
    parents_ok = parents == [old_head] if payload["mode"] == "new" else parents == old_parents
    if not parents_ok:
        raise ExecError(
            "parent_mismatch",
            f"提交 {sha[:12]} 的父提交关系与预期不符（{payload['mode']} 模式）。不要推送这个提交。",
        )
    receipt = {
        "kind": KIND_COMMIT,
        "action_id": args.action,
        "stage_action_id": payload.get("stage_action_id"),
        "root": str(root),
        "sha": sha,
        "old_head": old_head,
        "tree": realized_tree,
        "change_id": change_id,
        "amend": payload["mode"] == "amend",
        "destination": payload["destination"],
    }
    _write_receipt("commit", args.action, receipt)
    gate.discard_action(args.action)
    return {
        "sha": sha,
        "old_head": old_head,
        "amend": payload["mode"] == "amend",
        "change_id": change_id,
        "subject": final_message.splitlines()[0] if final_message else "",
        "message": final_message,
        "destination": _redacted(payload["destination"]),
    }


# ---------------------------------------------------------------- push：登记与执行


def plan_push(args: argparse.Namespace) -> dict[str, Any]:
    sha = args.sha.strip().lower()
    if not SHA_RE.fullmatch(sha):
        raise ExecError("bad_sha", f"需要完整的 40 位提交 SHA，得到：{args.sha!r}")
    root = repo_root()
    receipt = _read_receipt("commit", args.commit_action)
    if receipt.get("root") != str(root):
        raise ExecError(
            "receipt_root_mismatch",
            f"commit 回执属于仓库 {receipt.get('root')}，当前仓库是 {root}。请在对应仓库里执行。",
        )
    if receipt.get("sha") != sha:
        raise ExecError(
            "sha_mismatch",
            f"--sha {sha} 与 commit 回执里的提交 {receipt.get('sha')} 不一致。请推送回执记录的那个提交。",
        )
    confirmed = phase0_local(root)
    tip = _git_text("rev-parse", "HEAD", cwd=root).strip()
    if tip != sha:
        raise ExecError("not_tip", f"{sha[:12]} 不是当前分支顶端（HEAD 是 {tip[:12]}），拒绝推送。")
    destination = _destination(confirmed)
    if destination != receipt.get("destination"):
        raise ExecError(
            "destination_changed_since_commit",
            "推送目标（分支/remote/URL/目标分支）与 commit 回执不一致。请重新走提交流程。",
        )
    review_ref = f"refs/for/{confirmed['dest_branch']}"
    payload = {
        "sha": sha,
        "review_ref": review_ref,
        "destination": destination,
        "root": str(root),
        "commit_action_id": args.commit_action,
    }
    summary = (
        "commit-gerrit：推送 Gerrit 评审\n"
        f"提交 {sha}\n"
        f"{sha} → {review_ref}\n"
        f"remote {confirmed['remote']}｜host {confirmed['host'] or '本地'}｜目标分支 {confirmed['dest_branch']}"
    )
    action = gate.create_action(
        KIND_PUSH,
        payload,
        question=f"是否把 {sha[:12]} 推送到 {review_ref} 创建/更新评审？",
        summary=summary,
        approve_label="确认推送",
    )
    return {
        "action_id": action["id"],
        "kind": KIND_PUSH,
        "question": action["question"],
        "summary": summary,
        "approve_label": action["approve_label"],
        "decline_label": action["decline_label"],
        "sha": sha,
        "review_ref": review_ref,
        "destination": _redacted(destination),
    }


def _verify_commit_lineage(root: Path, commit_receipt: dict[str, Any]) -> None:
    """从现场复核提交的父子关系与结果树：new 的父是旧 HEAD，amend 保留原父集。"""
    sha = commit_receipt["sha"]
    old_head = commit_receipt["old_head"]
    parents = _git_text("log", "-1", "--format=%P", sha, cwd=root).split()
    old_parents = _git_text("log", "-1", "--format=%P", old_head, cwd=root).split()
    expected = old_parents if commit_receipt.get("amend") else [old_head]
    if parents != expected:
        raise ExecError(
            "parent_mismatch",
            f"提交 {sha[:12]} 的父提交关系与预期不符（{commit_receipt.get('amend') and 'amend' or 'new'} 模式）。不要推送。",
        )
    if _git_text("rev-parse", f"{sha}^{{tree}}", cwd=root).strip() != commit_receipt.get("tree"):
        raise ExecError("tree_mismatch", f"提交 {sha[:12]} 的结果树与回执不一致。不要推送。")


def run_push(args: argparse.Namespace) -> dict[str, Any]:
    action = gate.load_action(args.action, KIND_PUSH)
    payload = action["payload"]
    root = repo_root()
    confirmed = phase0_local(root)
    tip = _git_text("rev-parse", "HEAD", cwd=root).strip()
    live = dict(payload, destination=_destination(confirmed), root=str(root))
    if tip != payload["sha"]:
        live = dict(live, sha=tip)
    gate.authorize(args.action, KIND_PUSH, live)
    commit_receipt = _read_receipt("commit", str(payload.get("commit_action_id") or ""))
    if commit_receipt.get("sha") != payload["sha"]:
        raise ExecError("sha_mismatch", "推送动作绑定的提交与 commit 回执不一致。不要推送。")
    _verify_commit_lineage(root, commit_receipt)
    refspec = f"{payload['sha']}:{payload['review_ref']}"
    result = subprocess.run(
        [
            "git",
            "push",
            "--receive-pack=gerrit receive-pack",
            "--no-follow-tags",
            payload["destination"]["remote"],
            refspec,
        ],
        cwd=root,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ExecError("push_failed", "git push 失败：" + result.stderr.decode("utf-8", "replace").strip())
    gate.discard_action(args.action)
    output = (result.stdout + result.stderr).decode("utf-8", "replace").strip()
    return {
        "sha": payload["sha"],
        "review_ref": payload["review_ref"],
        "remote": confirmed["remote"],
        "dest_branch": confirmed["dest_branch"],
        "push_output": output,
        "note": "干净版本补丁功能测试与 Review+1 状态未知时保持未知，不得报告为已通过。",
    }


# ---------------------------------------------------------------- 命令行


def _emit(data: dict[str, Any]) -> None:
    print(json.dumps(dict({"ok": True}, **data), ensure_ascii=False, indent=2))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="commit-gerrit 执行器（门禁脚本）")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("preflight", help="阶段零只读预检：本地硬检查 + 目标分支探测（不登记动作）")

    stage = commands.add_parser("stage", help="登记/执行暂存")
    stage.add_argument("--plan", action="store_true", help="只读登记待确认动作（含唯一一次 ls-remote 目标探测）")
    stage.add_argument("--action", metavar="ID", help="执行已确认的暂存动作")
    stage.add_argument("--issue", help="Redmine 问题号（单个正整数）")
    stage.add_argument("--mode", choices=["new", "amend"], default="new", help="后续 commit-plan 的提交方式")
    stage.add_argument("--scope", nargs="+", metavar="PATH", help="用户指定的提交范围")
    stage.add_argument("--message-file", metavar="F", help="完整消息（new）或追加段（amend）的文件，放在仓库外")

    commit_plan = commands.add_parser("commit-plan", help="登记提交动作（核验 stage 回执后登记）")
    commit_plan.add_argument("--mode", choices=["new", "amend"], required=True)
    commit_plan.add_argument("--stage-action", metavar="ID", required=True, help="已成功执行的 stage 动作编号")

    commit = commands.add_parser("commit", help="执行已确认的提交动作")
    commit.add_argument("--action", metavar="ID", required=True)

    push_plan = commands.add_parser("push-plan", help="登记推送动作（核验 commit 回执后登记）")
    push_plan.add_argument("--commit-action", metavar="ID", required=True, help="已成功执行的 commit 动作编号")
    push_plan.add_argument("--sha", required=True, help="commit 输出的完整 SHA")

    push = commands.add_parser("push", help="执行已确认的推送动作")
    push.add_argument("--action", metavar="ID", required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "preflight":
        return run_preflight(args)
    if args.command == "stage":
        if args.action:
            return run_stage(args)
        if not args.plan:
            raise ExecError("usage", "stage 需要 --plan 或 --action。")
        if not args.issue:
            raise ExecError("usage", "stage --plan 需要 --issue（Redmine 问题号）。")
        if not args.message_file:
            raise ExecError("usage", "stage --plan 需要 --message-file（完整草稿消息）。")
        return plan_stage(args)
    if args.command == "commit-plan":
        return plan_commit(args)
    if args.command == "commit":
        return run_commit(args)
    if args.command == "push-plan":
        return plan_push(args)
    if args.command == "push":
        return run_push(args)
    raise ExecError("usage", f"未知子命令：{args.command}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _run(args)
    except gate.GateError as error:
        payload = {"ok": False, "error": error.code, "message": error.message}
        if error.changed:
            payload["changed"] = error.changed
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    except redmine.RedmineError as error:
        print(json.dumps({"ok": False, "error": error.code, "message": error.message}, ensure_ascii=False, indent=2))
        return 1
    except ExecError as error:
        print(json.dumps({"ok": False, "error": error.code, "message": error.message}, ensure_ascii=False, indent=2))
        return 1
    _emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
