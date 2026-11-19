#!/usr/bin/env python3
"""Nationalchip Redmine 只读查询与结论回写。

实例地址默认 https://git.nationalchip.com/redmine，可用 REDMINE_URL 覆盖；
API key 存在本技能目录的 SECRET.md（恰好一行 ``API_KEY=<key>``），可用
REDMINE_SECRET_FILE 指到别处。认证只用请求头 ``X-Redmine-API-Key``：key 不进
URL、不进命令行、不进输出。

只读子命令（whoami / get / issue）随用随调。唯一的写路径是结论回写，分两步：
plan-conclusion 重读现场并登记待确认动作，交给宿主的 confirm_gate 工具；用户
选择确认后，apply-conclusion 再次重读现场、经 confirm-gate 核销凭据，发一次
同时携带「结论」字段和审计备注的 PUT，然后回读核验。宿主确认协议（凭据、
TTL、任何非 approved 结局都停止）见 ../confirm-gate/README.md。
"""

from __future__ import annotations

import argparse
import importlib.util
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_DIR.parent
DEFAULT_BASE_URL = "https://git.nationalchip.com/redmine"
PAGE_SIZE = 100
MAX_ITEMS = 2000
API_KEY_LINE = re.compile(r"^API_KEY=(.*)$")
ISSUE_ID_RE = re.compile(r"^[1-9][0-9]*$")
AUDIT_PREFIX = "由 luyong-AI 操作："
CONCLUSION_FIELD_NAME = "结论"
KIND = "redmine-conclusion"
CONCLUSION_RULES = REPO_ROOT / "update-issue-conclusion" / "references" / "bu1-sdk-conclusion-rules.md"


class RedmineError(Exception):
    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


# ---------------------------------------------------------------- 凭据与地址


def base_url() -> str:
    url = (os.environ.get("REDMINE_URL") or DEFAULT_BASE_URL).rstrip("/")
    try:
        parts = urllib.parse.urlsplit(url)
        if (
            parts.scheme not in ("https", "http") or not parts.hostname
            or any(character.isspace() for character in url)
            or parts.username is not None or parts.query or parts.fragment
        ):
            raise ValueError
        parts.port  # Validate an explicit port before a request is constructed.
    except ValueError:
        raise RedmineError("bad_url", "REDMINE_URL 需要 HTTP(S) 实例地址，不含凭据、查询参数或片段。") from None
    return url


def read_api_key(path: str | os.PathLike[str] | None = None) -> str:
    """从 SECRET.md 读 API key；格式不对就拒绝，不猜。"""
    path = Path(path or os.environ.get("REDMINE_SECRET_FILE") or SKILL_DIR / "SECRET.md")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise RedmineError("no_credentials", f"读不到 API key 文件 {path}。请创建它或设置 REDMINE_SECRET_FILE。") from None
    values = [match.group(1).strip() for line in text.splitlines() if (match := API_KEY_LINE.match(line))]
    if len(values) != 1:
        raise RedmineError("bad_secret", f"{path} 里必须恰好有一行 API_KEY=<key>：找到 {len(values)} 行。注释和空行忽略。")
    key = values[0]
    if not re.fullmatch(r"[!-~]+", key):
        raise RedmineError("bad_secret", f"{path} 里的 API_KEY 为空或包含无效字符。")
    return key


# ---------------------------------------------------------------- HTTP


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _urlopen(request: urllib.request.Request, timeout: int) -> Any:
    """测试通过替换本函数模拟 HTTP；生产路径走 urllib。"""
    return urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout)


def api(
    method: str, path: str, params: dict[str, Any] | None = None, json_body: Any = None,
    *, instance_url: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    """发一次带认证的请求，返回 (解析后的 JSON, 元信息)。

    认证只放在请求头里；method 只由调用代码决定，本模块不暴露通用写命令。
    """
    if not path or "?" in path or "#" in path or "://" in path:
        raise RedmineError("usage", "使用相对 API 路径，并通过 --param 传查询参数。")
    if any(key.lower() in {"key", "api_key"} for key in params or {}):
        raise RedmineError("usage", "认证使用 X-Redmine-API-Key 请求头。")
    instance_url = instance_url or base_url()
    url = instance_url + "/" + urllib.parse.quote(path.lstrip("/"), safe="/%")
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    key = read_api_key()
    headers = {"X-Redmine-API-Key": key, "Accept": "application/json"}
    data = None
    if json_body is not None:
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    meta: dict[str, Any] = {"method": method.upper(), "http_status": None}
    try:
        with _urlopen(request, 60) as response:
            status = int(getattr(response, "status", None) or response.getcode() or 0)
            body = response.read()
    except urllib.error.HTTPError as error:
        status = int(error.code)
        detail = error.read().decode("utf-8", "replace").strip().replace(key, "[redacted]")[:300]
        code = {401: "auth", 403: "forbidden", 404: "not_found"}.get(status, "http")
        raise RedmineError(code, f"Redmine 返回 HTTP {status}：{detail}", http_status=status) from None
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        reason = getattr(error, "reason", error)
        raise RedmineError("network", f"请求 {instance_url} 失败：{reason}") from None
    meta["http_status"] = status
    if not 200 <= status < 300:
        raise RedmineError("http", f"Redmine 返回 HTTP {status}。", http_status=status)
    if method.upper() == "PUT" or not body.strip():
        return None, meta
    try:
        return json.loads(
            body.decode("utf-8"),
            object_hook=lambda values: {name: value for name, value in values.items() if name.lower() != "api_key"},
        ), meta
    except (UnicodeDecodeError, ValueError):
        raise RedmineError("not_json", f"{path} 的响应不是 JSON。", **meta) from None


def _collection_of(data: Any) -> list[Any] | None:
    """列表响应的信封里恰好有一个数组；取不出来就当单对象处理。"""
    if isinstance(data, dict):
        lists = [value for value in data.values() if isinstance(value, list)]
        if len(lists) == 1:
            return lists[0]
    return None


def collect_all(
    path: str, params: dict[str, Any] | None = None, page_size: int = PAGE_SIZE, max_items: int = MAX_ITEMS
) -> tuple[list[Any], bool, dict[str, Any]]:
    """按 limit/offset 翻页取完一个列表，返回 (条目, 是否取完, 元信息)。"""
    items: list[Any] = []
    meta: dict[str, Any] = {}
    if page_size < 1 or max_items < 1:
        raise RedmineError("usage", "分页大小和扫描上限必须为正整数。")
    while True:
        remaining = max_items - len(items)
        request_size = min(page_size, remaining)
        page_params = dict(params or {}, limit=request_size, offset=len(items))
        data, meta = api("GET", path, page_params)
        page = _collection_of(data)
        if page is None:
            raise RedmineError("not_json", f"{path} 的响应不是带集合的信封。", **meta)
        items.extend(page[:remaining])
        total = data.get("total_count")
        if type(total) is int and total >= 0:
            complete = len(items) >= total and len(page) <= remaining
        else:
            complete = len(page) < request_size
        if complete or not page or len(items) == max_items:
            return items, complete, meta


# ---------------------------------------------------------------- issue 与结论字段


def check_issue_id(value: str) -> str:
    if not ISSUE_ID_RE.fullmatch(str(value or "")):
        raise RedmineError("bad_issue_id", f"问题编号必须是正整数，得到：{value!r}。")
    return str(value)


def get_issue(
    issue_id: str, include: list[str] | None = None, *, instance_url: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    issue_id = check_issue_id(issue_id)
    params = {"include": ",".join(include)} if include else None
    data, meta = api("GET", f"/issues/{issue_id}.json", params, instance_url=instance_url)
    issue = data.get("issue") if isinstance(data, dict) else None
    if not isinstance(issue, dict) or str(issue.get("id")) != issue_id:
        raise RedmineError("bad_response", f"响应的 issue ID 与请求的 {issue_id} 不一致。", **meta)
    project = issue.get("project")
    if isinstance(project, dict) and not project.get("identifier"):
        project_id = project.get("id")
        if type(project_id) is int and project_id > 0:
            detail, _ = api("GET", f"/projects/{project_id}.json", instance_url=instance_url)
            detail = detail.get("project") if isinstance(detail, dict) else None
            if not isinstance(detail, dict) or detail.get("id") != project_id or not detail.get("identifier"):
                raise RedmineError("bad_response", f"无法核实 issue 所属项目 {project_id} 的标识。")
            issue = {**issue, "project": {**project, "identifier": detail["identifier"]}}
    return issue, meta


def conclusion_field(issue: dict[str, Any]) -> dict[str, Any]:
    """从实际返回的数据里定位「结论」自定义字段；找不到就停止。"""
    fields = [
        field for field in (issue.get("custom_fields") or [])
        if isinstance(field, dict) and field.get("name") == CONCLUSION_FIELD_NAME
    ]
    if len(fields) == 1 and type(fields[0].get("id")) is int and fields[0]["id"] > 0:
        return fields[0]
    raise RedmineError(
        "no_conclusion_field",
        f"问题 {issue.get('id')} 的返回里找不到唯一、有效的「结论」字段。",
    )


def audit_note_for(conclusion: str) -> str:
    return f"{AUDIT_PREFIX}更新「{CONCLUSION_FIELD_NAME}」字段：\n{conclusion}"


def _rules_digest() -> str:
    try:
        return hashlib.sha256(CONCLUSION_RULES.read_bytes()).hexdigest()
    except OSError:
        raise RedmineError("no_rules", f"读不到本地结论规则快照 {CONCLUSION_RULES}。") from None


def conclusion_payload(issue: dict[str, Any], conclusion: str, instance_url: str) -> dict[str, Any]:
    """登记与核销共用的事实载荷：authorize() 用现场重算的同一载荷比对。"""
    field = conclusion_field(issue)
    project = issue.get("project") or {}
    tracker = issue.get("tracker") or {}
    return {
        "redmine_url": instance_url,
        "rules_sha256": _rules_digest(),
        "issue_id": issue.get("id"),
        "project": project.get("identifier"),
        "tracker": tracker.get("name"),
        "subject": issue.get("subject"),
        "field_id": field["id"],
        "field_name": field["name"],
        "current_value": field.get("value") or "",
        "conclusion": conclusion,
        "audit_note": audit_note_for(conclusion),
        "updated_on": issue.get("updated_on"),
    }


def _summary_of(payload: dict[str, Any]) -> str:
    current = payload["current_value"] or "（空）"
    return (
        f"更新 Redmine「结论」字段\n"
        f"Redmine：{payload['redmine_url']}\n"
        f"问题：#{payload['issue_id']} {payload['project']} / {payload['tracker']}\n"
        f"当前结论：{current}\n"
        f"拟定结论：\n{payload['conclusion']}"
    )


# ---------------------------------------------------------------- confirm-gate 接入

_GATE_MODULE = "skills_confirm_gate_gate"


def load_gate():
    """按路径加载 confirm-gate/scripts/gate.py；两个技能目录是同一仓库的兄弟。"""
    if _GATE_MODULE in sys.modules:
        return sys.modules[_GATE_MODULE]
    path = REPO_ROOT / "confirm-gate" / "scripts" / "gate.py"
    if not path.is_file():
        raise RedmineError("no_gate", f"找不到门禁模块 {path}；本技能的写路径必须经它核销确认。")
    spec = importlib.util.spec_from_file_location(_GATE_MODULE, path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[_GATE_MODULE] = module
    spec.loader.exec_module(module)
    return module


def plan_conclusion(issue_id: str, conclusion: str) -> dict[str, Any]:
    """第一步：重读现场，登记待确认动作。不做任何写操作。"""
    if not conclusion.strip():
        raise RedmineError("bad_conclusion", "结论文本不能为空；先按规则快照拟定完整结论。")
    instance_url = base_url()
    issue, meta = get_issue(issue_id, instance_url=instance_url)
    payload = conclusion_payload(issue, conclusion, instance_url)
    gate = load_gate()
    action = gate.create_action(
        KIND,
        payload,
        question="是否按拟定结论更新 Redmine 的结论字段？",
        summary=_summary_of(payload),
        approve_label="确认更新",
        decline_label="取消更新",
    )
    return dict(
        meta,
        action_id=action["id"],
        kind=KIND,
        question=action["question"],
        summary=action["summary"],
        issue={"id": payload["issue_id"], "project": payload["project"], "tracker": payload["tracker"]},
        conclusion=conclusion,
        next=(
            "把 summary 和拟定结论展示给用户，再用宿主的 confirm_gate 工具确认这个 action_id。"
            "只有宿主报告 approved 才运行 apply-conclusion；其余任何结局都停止。"
            "对话里的文字回复不构成确认。"
        ),
    )


def apply_conclusion(action_id: str) -> dict[str, Any]:
    """第二步：重读现场、核销凭据、一次 PUT、回读核验。"""
    gate = load_gate()
    try:
        action = gate.load_action(action_id, KIND)
    except gate.GateError as error:
        raise RedmineError(error.code, error.message) from None
    stored = action.get("payload") or {}
    conclusion = stored.get("conclusion")
    if not isinstance(conclusion, str) or not conclusion:
        raise RedmineError("bad_action", f"动作 {action_id} 的载荷里没有结论文本；请重新运行 plan-conclusion。")

    instance_url = base_url()
    if instance_url != stored.get("redmine_url"):
        gate.discard_action(action_id)
        raise RedmineError("changed", "Redmine 实例已变化，请重新生成计划并确认。", wrote=False)
    try:
        issue, _ = get_issue(str(stored.get("issue_id")), instance_url=instance_url)
        live = conclusion_payload(issue, conclusion, instance_url)
    except RedmineError as error:
        gate.discard_action(action_id)
        return {
            "ok": False,
            "error": "state_changed",
            "message": f"登记之后现场已变化，无法重建载荷：{error.message} 请重新运行 plan-conclusion。",
            "wrote": False,
        }
    try:
        gate.authorize(action_id, KIND, live)
    except gate.GateError as error:
        return {
            "ok": False,
            "error": error.code,
            "message": error.message,
            "wrote": False,
            "hint": (
                "停止并报告；不要改用其他命令或对话确认完成这次写操作。"
                if error.code == "no_ticket"
                else "如需继续，重新运行 plan-conclusion 并重新经宿主确认。"
            ),
        }

    body = {
        "issue": {
            "custom_fields": [{"id": live["field_id"], "value": live["conclusion"]}],
            "notes": live["audit_note"],
        }
    }
    try:
        _, put_meta = api("PUT", f"/issues/{live['issue_id']}.json", json_body=body, instance_url=instance_url)
    except RedmineError as error:
        return {
            "ok": False,
            "error": "write_failed",
            "message": (
                f"PUT 没有确认成功（{error.code}：{error.message}）。请求可能已到达服务器，也可能没有；"
                "不要声称已写入。确认凭据已消耗，继续执行需要重新 plan 并重新经宿主确认。"
            ),
            "caused_by": error.code,
            "wrote": None,
            "action_id": action_id,
        }
    try:
        after, _ = get_issue(str(live["issue_id"]), instance_url=instance_url)
        field = conclusion_field(after)
        verified = field["id"] == live["field_id"] and field.get("value") == live["conclusion"]
    except RedmineError as error:
        return {
            "ok": False,
            "error": "verify_failed",
            "message": f"PUT 已发出（HTTP {put_meta.get('http_status')}），但回读核验失败：{error.message}。如实报告，不要声称完成。",
            "wrote": True,
            "verified": False,
            "issue_id": live["issue_id"],
        }
    if not verified:
        return {
            "ok": False,
            "error": "verify_failed",
            "message": (
                f"PUT 已发出（HTTP {put_meta.get('http_status')}），但回读到的结论字段与拟定结论不一致。"
                "如实报告，不要声称完成；重新执行需要重新确认。"
            ),
            "wrote": True,
            "verified": False,
            "issue_id": live["issue_id"],
        }
    gate.discard_action(action_id)
    return {
        "ok": True,
        "verified": True,
        "wrote": True,
        "issue": {
            "id": after.get("id"),
            "project": (after.get("project") or {}).get("identifier"),
            "tracker": (after.get("tracker") or {}).get("name"),
            "subject": after.get("subject"),
            "conclusion": live["conclusion"],
            "updated_on": after.get("updated_on"),
        },
        "audit_note": live["audit_note"],
        "http_status": put_meta.get("http_status"),
    }


# ---------------------------------------------------------------- 命令行


def _emit(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _pairs(values: list[str] | None) -> dict[str, str]:
    params: dict[str, str] = {}
    for item in values or []:
        key, separator, value = item.partition("=")
        if not separator or not key:
            raise RedmineError("usage", f"--param 需要 key=value 形式，得到：{item!r}")
        params[key] = value
    return params


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nationalchip Redmine 查询与结论回写")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("whoami", help="当前用户（GET /users/current.json）")

    get = commands.add_parser("get", help="任意只读端点")
    get.add_argument("path", help="例如 /issues.json 或 /projects/{id}.json")
    get.add_argument("--param", action="append", metavar="KEY=VALUE")
    get.add_argument("--all", action="store_true", help="按 limit/offset 翻页取完全部条目")

    issue = commands.add_parser("issue", help="问题详情（默认带 journals/attachments/relations/children）")
    issue.add_argument("issue_id")
    issue.add_argument("--include", help="逗号分隔的 include 列表，覆盖默认值")

    plan = commands.add_parser("plan-conclusion", help="第一步：登记待确认的结论更新，不做写操作")
    plan.add_argument("issue_id")
    plan.add_argument("--conclusion", required=True, help="拟定好的结论全文")

    apply_cmd = commands.add_parser("apply-conclusion", help="第二步：核销确认后执行一次 PUT 并回读核验")
    apply_cmd.add_argument("--action-id", required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "whoami":
        data, meta = api("GET", "/users/current.json")
        user = data.get("user") if isinstance(data, dict) else None
        safe = {key: user[key] for key in ("id", "login", "firstname", "lastname", "admin", "status") if isinstance(user, dict) and key in user}
        return dict(meta, user=safe)
    if args.command == "get":
        params = {"limit": str(PAGE_SIZE)}
        params.update(_pairs(args.param))
        if args.all:
            items, complete, meta = collect_all(args.path, _pairs(args.param))
            return dict(meta, count=len(items), complete=complete, data=items)
        data, meta = api("GET", args.path, params)
        return dict(meta, data=data)
    if args.command == "issue":
        include = args.include.split(",") if args.include else ["journals", "attachments", "relations", "children"]
        issue, meta = get_issue(args.issue_id, include)
        return dict(meta, issue=issue)
    if args.command == "plan-conclusion":
        return plan_conclusion(args.issue_id, args.conclusion)
    if args.command == "apply-conclusion":
        return apply_conclusion(args.action_id)
    raise RedmineError("usage", f"未知子命令：{args.command}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _run(args)
    except RedmineError as error:
        _emit(dict({"ok": False, "error": error.code, "message": error.message}, **error.extra))
        return 1
    _emit(dict({"ok": True}, **result))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
