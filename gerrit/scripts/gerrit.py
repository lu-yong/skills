#!/usr/bin/env python3
"""Nationalchip Gerrit 只读查询。

实例、认证方式和 TLS 处理登记在 ../instances.json。凭据来自用户自己的 netrc
文件（GERRIT_NETRC_FILE，默认 ~/.netrc），由 curl 读取，不经过本脚本的输出。
所有子命令只发 GET 请求，输出一个 JSON 对象；patch 子命令输出补丁原文。
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

INSTANCES_FILE = Path(__file__).resolve().parent.parent / "instances.json"
XSSI_PREFIX = ")]}'"
PAGE_SIZE = 100
MAX_RESULTS = 5000
CHANGE_ID_LINE = re.compile(r"^Change-Id: (I[0-9a-f]{40})$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class GerritError(Exception):
    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


# ---------------------------------------------------------------- 实例登记


def load_instances() -> dict[str, Any]:
    """读取实例登记，并给每个实例补上从 base_url 得出的 host。"""
    with open(INSTANCES_FILE, encoding="utf-8") as handle:
        data = json.load(handle)
    instances = {}
    for name, config in data["instances"].items():
        base_url = config["base_url"].rstrip("/")
        host = urlsplit(base_url).hostname
        if not host:
            raise GerritError("bad_instances", f"实例 {name} 的 base_url 没有主机名：{base_url}")
        aliases = [str(alias).lower() for alias in config.get("host_aliases", [])]
        instances[name] = dict(config, base_url=base_url, host=host.lower(), host_aliases=aliases)
    return {
        "instances": instances,
        "unmapped_push_hosts": [str(host).lower() for host in data.get("unmapped_push_hosts", [])],
    }


def push_hosts() -> set[str]:
    """允许作为 Gerrit 评审推送目标的全部主机。"""
    data = load_instances()
    hosts = set(data["unmapped_push_hosts"])
    for config in data["instances"].values():
        hosts.add(config["host"])
        hosts.update(config["host_aliases"])
    return hosts


def instance_for_host(host: str | None) -> str | None:
    if not host:
        return None
    for name, config in load_instances()["instances"].items():
        if host.lower() == config["host"] or host.lower() in config["host_aliases"]:
            return name
    return None


# ---------------------------------------------------------------- remote URL


def parse_remote(url: str) -> dict[str, str | None]:
    """拆出 git remote URL 的协议、主机和路径。本地路径的 host 为 None。"""
    url = url.strip()
    if "://" in url:
        parts = urlsplit(url)
        return {
            "scheme": parts.scheme.lower(),
            "host": parts.hostname.lower() if parts.hostname else None,
            "path": parts.path,
        }
    scp_like = re.match(r"^(?:[^@/:]+@)?([^@/:]+):(.*)$", url)
    if scp_like:
        return {"scheme": "ssh", "host": scp_like.group(1).lower(), "path": scp_like.group(2)}
    return {"scheme": "file", "host": None, "path": url}


def redact_url(text: str) -> str:
    """去掉 URL 里内嵌的用户名和密码。"""
    return re.sub(r"(://)[^/@\s]+@", r"\1***@", text)


def project_from_remote(remote: dict[str, str | None], instance: dict[str, Any]) -> str | None:
    """从 remote 路径推出 Gerrit 项目名；路径不像这个实例的地址时返回 None。"""
    path = (remote.get("path") or "").strip("/")
    if remote.get("scheme") in ("http", "https"):
        base_path = urlsplit(instance["base_url"]).path.strip("/")
        if base_path:
            if path != base_path and not path.startswith(base_path + "/"):
                return None
            path = path[len(base_path) :].strip("/")
        if path.startswith("a/"):
            path = path[2:]
    if path.endswith(".git"):
        path = path[: -len(".git")]
    return path or None


# ---------------------------------------------------------------- 本地仓库


def _git(cwd: str | os.PathLike[str] | None, *args: str) -> tuple[int, str]:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return result.returncode, result.stdout.decode("utf-8", "replace")


def change_id_of(message: str) -> str | None:
    """提交消息最后一段里的 Change-Id；没有或不唯一时返回 None。"""
    paragraphs = [block for block in re.split(r"\n\s*\n", message.strip()) if block.strip()]
    if not paragraphs:
        return None
    found = [match.group(1) for line in paragraphs[-1].splitlines() if (match := CHANGE_ID_LINE.match(line.strip()))]
    return found[0] if len(found) == 1 else None


def repo_context(cwd: str | os.PathLike[str] | None = None, commit: str = "HEAD") -> dict[str, Any]:
    """当前仓库里与 Gerrit 查询有关的事实。推不出的项为 None。"""
    code, root = _git(cwd, "rev-parse", "--show-toplevel")
    if code != 0:
        raise GerritError("not_a_repository", "当前目录不在 Git 仓库里。请切到相关仓库，或显式给出查询参数。")
    root = root.strip()
    branch = _git(root, "branch", "--show-current")[1].strip() or None

    remote = None
    if branch:
        remote = _git(root, "config", "--get", f"branch.{branch}.remote")[1].strip() or None
    if not remote:
        remotes = _git(root, "remote")[1].split()
        remote = remotes[0] if len(remotes) == 1 else None

    target = None
    if branch:
        merges = _git(root, "config", "--get-all", f"branch.{branch}.merge")[1].strip()
        merge_refs = set(merges.splitlines())
        if len(merge_refs) == 1:
            target = merge_refs.pop().removeprefix("refs/heads/") or None

    push_url = host = instance = project = None
    if remote:
        code, urls = _git(root, "remote", "get-url", "--push", "--all", remote)
        candidates = [line for line in urls.splitlines() if line.strip()] if code == 0 else []
        if len(candidates) == 1:
            push_url = candidates[0].strip()
            parsed = parse_remote(push_url)
            host = parsed["host"]
            instance = instance_for_host(host)
            if instance:
                project = project_from_remote(parsed, load_instances()["instances"][instance])

    code, sha = _git(root, "rev-parse", "--verify", f"{commit}^{{commit}}")
    sha = sha.strip() if code == 0 else None
    change_id = None
    if sha:
        change_id = change_id_of(_git(root, "log", "-1", "--format=%B", sha)[1])

    return {
        "root": root,
        "branch": branch,
        "remote": remote,
        "push_url": redact_url(push_url) if push_url else None,
        "host": host,
        "instance": instance,
        "project": project,
        "target_branch": target,
        "commit": sha,
        "change_id": change_id,
    }


# ---------------------------------------------------------------- HTTP


def _netrc_file() -> str:
    path = os.environ.get("GERRIT_NETRC_FILE") or os.path.join(os.path.expanduser("~"), ".netrc")
    if not os.access(path, os.R_OK):
        raise GerritError("no_credentials", f"读不到 netrc 文件 {path}。请先配置 GERRIT_NETRC_FILE 或 ~/.netrc。")
    try:
        if os.stat(path).st_mode & 0o077:
            print(f"警告：{path} 对其他用户可读，建议 chmod 600。", file=sys.stderr)
    except OSError:
        pass
    return path


def _curl(url: str, params: list[tuple[str, str]], netrc: str, digest: bool, insecure: bool) -> tuple[int, bytes, str]:
    command = [
        "curl",
        "--disable",
        "--globoff",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "15",
        "--max-time",
        "120",
        "--netrc-file",
        netrc,
        "--write-out",
        "\n%{http_code}",
        "--get",
    ]
    if digest:
        command.append("--digest")
    if insecure:
        command.append("--insecure")
    for key, value in params:
        command += ["--data-urlencode", f"{key}={value}"]
    command.append(url)
    try:
        result = subprocess.run(command, capture_output=True)
    except FileNotFoundError:
        raise GerritError("curl_missing", "找不到 curl 命令。") from None
    return result.returncode, result.stdout, result.stderr.decode("utf-8", "replace").strip()


def request(instance_name: str, endpoint: str, params: list[tuple[str, str]] | None = None) -> tuple[bytes, dict[str, Any]]:
    """对指定实例发一次带认证的 GET，返回 (响应体, 元信息)。"""
    instances = load_instances()["instances"]
    if instance_name not in instances:
        raise GerritError("unknown_instance", f"没有登记实例 {instance_name!r}。可用：{'、'.join(instances)}。")
    instance = instances[instance_name]
    url = f"{instance['base_url']}/a/{endpoint.lstrip('/')}"
    netrc = _netrc_file()
    digest = instance.get("auth") == "digest"
    meta = {"instance": instance_name, "tls_verified": True}

    code, output, error = _curl(url, params or [], netrc, digest, insecure=False)
    if code == 60:
        if not instance.get("insecure_tls_fallback"):
            raise GerritError("tls", f"{instance['host']} 的证书校验失败：{error}", **meta)
        print(
            f"警告：{instance['host']} 的证书校验失败，已按该实例的登记改用不校验证书的连接。",
            file=sys.stderr,
        )
        meta["tls_verified"] = False
        code, output, error = _curl(url, params or [], netrc, digest, insecure=True)
    if code != 0:
        raise GerritError("network", f"请求 {instance['host']} 失败（curl 退出码 {code}）：{error}", **meta)

    body, _, status_text = output.rpartition(b"\n")
    status = int(status_text) if status_text.isdigit() else 0
    meta["http_status"] = status
    if status == 401:
        raise GerritError("auth", f"认证失败（HTTP 401）。检查 netrc 文件里 {instance['host']} 的条目。", **meta)
    if not 200 <= status < 300:
        detail = body.decode("utf-8", "replace").strip()[:500]
        code_name = {403: "forbidden", 404: "not_found"}.get(status, "http")
        raise GerritError(code_name, f"{instance['host']} 返回 HTTP {status}：{detail}", **meta)
    return body, meta


def parse_json(body: bytes) -> Any:
    """去掉 XSSI 前缀后解析 JSON；没有前缀的响应原样解析。"""
    text = body.decode("utf-8")
    if text.startswith(XSSI_PREFIX):
        text = text[len(XSSI_PREFIX) :]
    return json.loads(text)


def get_json(instance: str, endpoint: str, params: list[tuple[str, str]] | None = None) -> tuple[Any, dict[str, Any]]:
    body, meta = request(instance, endpoint, params)
    try:
        return parse_json(body), meta
    except (UnicodeDecodeError, ValueError):
        raise GerritError("not_json", f"{endpoint} 的响应不是 JSON。", **meta) from None


def change_path(change: str, suffix: str = "") -> str:
    return f"changes/{quote(str(change), safe='')}{suffix}"


def query_changes(
    instance: str, query: str, options: list[str] | None = None, limit: int | None = PAGE_SIZE
) -> tuple[list[dict[str, Any]], bool, dict[str, Any]]:
    """按查询条件列出变更，翻页直到取完或达到 limit。

    返回 (变更列表, 是否取完, 元信息)。limit 为 None 表示取完全部，上限 MAX_RESULTS。
    """
    wanted = MAX_RESULTS if limit is None else limit
    changes: list[dict[str, Any]] = []
    meta: dict[str, Any] = {"instance": instance, "tls_verified": True}
    start = 0
    while True:
        page_size = min(PAGE_SIZE, wanted - len(changes))
        if page_size <= 0:
            return changes, False, meta
        params = [("q", query), ("n", str(page_size)), ("start", str(start))]
        params += [("o", option) for option in options or []]
        page, page_meta = get_json(instance, "changes/", params)
        meta["tls_verified"] = meta["tls_verified"] and page_meta["tls_verified"]
        if not isinstance(page, list) or any(not isinstance(change, dict) for change in page):
            raise GerritError("not_json", "变更查询的响应不是变更对象列表。", **meta)
        more = bool(page) and bool(page[-1].get("_more_changes"))
        for change in page:
            change.pop("_more_changes", None)
        changes += page
        start += len(page)
        if not page or (not more and len(page) < page_size):
            return changes, True, meta
        if not more and len(changes) >= wanted:
            # 整页返回但服务器没有标记后续，再取一页才能确认是否取完。
            probe, probe_meta = get_json(instance, "changes/", [("q", query), ("n", "1"), ("start", str(start))])
            meta["tls_verified"] = meta["tls_verified"] and probe_meta["tls_verified"]
            if not isinstance(probe, list):
                raise GerritError("not_json", "变更查询的响应不是列表。", **meta)
            return changes, not probe, meta
        if len(changes) >= wanted:
            return changes, False, meta


def fetch_patch(instance: str, change: str, revision: str) -> tuple[bytes, dict[str, Any]]:
    """解出 Gerrit 返回的 base64 补丁并保留原始字节。"""
    body, meta = request(instance, change_path(change, f"/revisions/{quote(revision, safe='')}/patch"))
    compact = b"".join(body.split())
    try:
        decoded = base64.b64decode(compact, validate=True) if compact else body
    except (binascii.Error, ValueError):
        decoded = body
    return decoded, meta


# ---------------------------------------------------------------- 提交对应的变更


def _brief(change: dict[str, Any]) -> dict[str, Any]:
    revisions = change.get("revisions")
    return {
        "number": change.get("_number"),
        "change_id": change.get("change_id"),
        "project": change.get("project"),
        "branch": change.get("branch"),
        "status": change.get("status"),
        "subject": change.get("subject"),
        "current_revision": change.get("current_revision"),
        "patchsets": (
            {sha: info.get("_number") for sha, info in revisions.items()} if isinstance(revisions, dict) else None
        ),
    }


def _candidate_detail(instance: str, number: int) -> tuple[dict[str, Any], dict[str, Any]]:
    detail, meta = get_json(instance, change_path(str(number), "/detail"), [("o", "ALL_REVISIONS")])
    if not isinstance(detail, dict) or detail.get("_number") != number:
        raise GerritError("bad_change_detail", f"详情返回的变更号与请求的 {number} 不一致。", **meta)
    fields = ("change_id", "project", "branch", "status", "current_revision")
    revisions = detail.get("revisions")
    if (
        any(not isinstance(detail.get(field), str) or not detail[field] for field in fields)
        or not isinstance(revisions, dict)
        or detail["current_revision"] not in revisions
        or any(not SHA_RE.fullmatch(sha) or not isinstance(info, dict) for sha, info in revisions.items())
    ):
        raise GerritError("bad_change_detail", f"变更 {number} 的详情缺少身份或完整 patchset 证据。", **meta)
    return detail, meta


def resolve_commit(
    *,
    instance: str | None = None,
    sha: str | None = None,
    change_id: str | None = None,
    project: str | None = None,
    branch: str | None = None,
    pick: int | None = None,
    cwd: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """找出本地提交在 Gerrit 上对应的变更，逐层收窄候选。

    没有显式给出的参数从当前仓库推出。推不出、需要用户决定的地方不猜：返回
    needs_instance / needs_project / needs_branch / ambiguous，并列出可选项。
    """
    context: dict[str, Any] = {}
    if None in (instance, sha, project, branch) or change_id is None:
        try:
            context = repo_context(cwd, sha or "HEAD")
        except GerritError:
            if sha is None:
                raise
    sources = {}

    def choose(name: str, explicit: Any, derived_key: str) -> Any:
        if explicit is not None:
            sources[name] = "argument"
            return explicit
        value = context.get(derived_key)
        sources[name] = "repository" if value is not None else "unknown"
        return value

    sha = choose("sha", sha, "commit")
    if not sha or not SHA_RE.fullmatch(sha):
        raise GerritError("bad_sha", f"需要完整的 40 位提交 SHA，得到：{sha!r}")
    change_id = choose("change_id", change_id, "change_id")
    instance = choose("instance", instance, "instance")
    project = choose("project", project, "project")
    if project is None and sources["instance"] == "argument" and context.get("push_url"):
        registry = load_instances()
        if context.get("host") in registry["unmapped_push_hosts"] and instance in registry["instances"]:
            project = project_from_remote(parse_remote(context["push_url"]), registry["instances"][instance])
            if project is not None:
                sources["project"] = "repository"
    branch = choose("branch", branch, "target_branch")

    result: dict[str, Any] = {
        "inputs": {
            "sha": sha,
            "change_id": change_id,
            "instance": instance,
            "project": project,
            "branch": branch,
            "sources": sources,
        },
        "layers": [],
    }
    if not instance:
        result.update(
            status="needs_instance",
            options=sorted(load_instances()["instances"]),
            remote_host=context.get("host"),
        )
        return result

    numbers: dict[int, None] = {}
    tls_verified = True
    queries = [f"commit:{sha}"] + ([f"change:{change_id}"] if change_id else [])
    for query in queries:
        changes, complete, meta = query_changes(instance, query, limit=None)
        tls_verified = tls_verified and meta["tls_verified"]
        if not complete:
            raise GerritError("incomplete", f"查询 {query} 的结果超过 {MAX_RESULTS} 条，候选列表不完整。")
        for change in changes:
            number = change.get("_number")
            if type(number) is not int or number < 1:
                raise GerritError("bad_change_detail", "变更查询返回了无效的变更号。", **meta)
            numbers[number] = None
    survivors = []
    for number in numbers:
        detail, meta = _candidate_detail(instance, number)
        survivors.append(detail)
        tls_verified = tls_verified and meta["tls_verified"]
    result["instance"] = instance
    result["tls_verified"] = tls_verified
    result["queries"] = queries

    def layer(name: str, expected: Any, keep) -> None:
        nonlocal survivors
        before = len(survivors)
        if expected is None:
            result["layers"].append({"layer": name, "applied": False, "candidates": before})
            return
        seen = sorted({str(change.get(name)) for change in survivors})
        survivors = [change for change in survivors if keep(change)]
        result["layers"].append(
            {"layer": name, "applied": True, "expected": expected, "seen": seen, "before": before, "after": len(survivors)}
        )

    layer("change_id", change_id, lambda change: change.get("change_id") == change_id)
    if project is None and survivors:
        result.update(
            status="needs_project",
            options=sorted({str(change.get("project")) for change in survivors}),
            candidates=[_brief(change) for change in survivors],
        )
        return result
    layer("project", project, lambda change: change.get("project") == project)
    if branch is None and survivors:
        result.update(
            status="needs_branch",
            options=sorted({str(change.get("branch")) for change in survivors}),
            candidates=[_brief(change) for change in survivors],
        )
        return result
    layer("branch", branch, lambda change: change.get("branch") == branch)

    exact = [change for change in survivors if sha in change["revisions"]]
    result["layers"].append(
        {"layer": "revision", "applied": True, "expected": sha, "before": len(survivors), "exact_matches": len(exact)}
    )
    if exact:
        survivors = exact

    basis = None
    if pick is not None:
        picked = [change for change in survivors if change.get("_number") == pick]
        if not picked:
            raise GerritError(
                "bad_pick",
                f"变更 {pick} 不在剩余候选里：{[change.get('_number') for change in survivors]}",
            )
        survivors, basis = picked, "user_selected"

    result["candidates"] = [_brief(change) for change in survivors]
    if not survivors:
        result["status"] = "none"
    elif len(survivors) > 1:
        result["status"] = "ambiguous"
    else:
        change = survivors[0]
        is_exact = change in exact
        selected = _brief(change)
        selected["revision"] = sha if is_exact else change.get("current_revision")
        selected["revision_basis"] = "exact" if is_exact else "current_revision"
        selected["selection_basis"] = basis or "unique"
        result.update(status="unique", change=selected)
    return result


# ---------------------------------------------------------------- 命令行


def _emit(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _pairs(values: list[str] | None) -> list[tuple[str, str]]:
    pairs = []
    for item in values or []:
        key, separator, value = item.partition("=")
        if not separator or not key:
            raise GerritError("usage", f"--param 需要 key=value 形式，得到：{item!r}")
        pairs.append((key, value))
    return pairs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nationalchip Gerrit 只读查询")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("instances", help="列出登记的实例")
    commands.add_parser("repo-context", help="当前仓库的 remote、实例、项目、目标分支和 HEAD")

    def with_instance(name: str, help_text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--instance", required=True, help="实例名，见 instances 子命令")
        return sub

    get = with_instance("get", "任意只读端点")
    get.add_argument("endpoint", help="例如 /accounts/self 或 /projects/")
    get.add_argument("--param", action="append", metavar="KEY=VALUE")

    change = with_instance("change", "变更详情")
    change.add_argument("change", help="变更号或 project~branch~Change-Id")
    change.add_argument("--option", action="append", metavar="O", help="附加的 o= 选项，例如 ALL_REVISIONS")

    query = with_instance("query", "按条件列出变更")
    query.add_argument("query", help="Gerrit 查询表达式，例如 'project:goxceed/loader status:open'")
    query.add_argument("--limit", type=int, default=PAGE_SIZE)
    query.add_argument("--all", action="store_true", help="翻页取完全部结果")
    query.add_argument("--option", action="append", metavar="O")

    files = with_instance("files", "某个补丁集改动的文件")
    files.add_argument("change")
    files.add_argument("--revision", default="current")

    patch = with_instance("patch", "某个补丁集的补丁原文")
    patch.add_argument("change")
    patch.add_argument("--revision", default="current")

    resolve = commands.add_parser("resolve-commit", help="找出本地提交对应的变更")
    resolve.add_argument("--instance")
    resolve.add_argument("--sha", help="完整提交 SHA，默认当前仓库的 HEAD")
    resolve.add_argument("--change-id")
    resolve.add_argument("--project")
    resolve.add_argument("--branch")
    resolve.add_argument("--pick", type=int, help="用户在多个候选里选定的变更号")
    return parser


def _run(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.command == "instances":
        data = load_instances()
        return {
            "instances": {
                name: {key: config[key] for key in ("label", "host", "base_url", "auth", "insecure_tls_fallback")}
                for name, config in data["instances"].items()
            },
            "unmapped_push_hosts": data["unmapped_push_hosts"],
        }
    if args.command == "repo-context":
        return repo_context()
    if args.command == "get":
        body, meta = request(args.instance, args.endpoint, _pairs(args.param))
        try:
            return dict(meta, data=parse_json(body))
        except (UnicodeDecodeError, ValueError):
            return dict(meta, text=body.decode("utf-8", "replace"))
    if args.command == "change":
        params = [("o", option) for option in args.option or []]
        data, meta = get_json(args.instance, change_path(args.change, "/detail"), params)
        return dict(meta, change=args.change, data=data)
    if args.command == "query":
        changes, complete, meta = query_changes(
            args.instance, args.query, args.option, limit=None if args.all else args.limit
        )
        return dict(meta, query=args.query, count=len(changes), complete=complete, data=changes)
    if args.command == "files":
        endpoint = change_path(args.change, f"/revisions/{quote(args.revision, safe='')}/files/")
        data, meta = get_json(args.instance, endpoint)
        return dict(meta, change=args.change, revision=args.revision, data=data)
    if args.command == "patch":
        patch, meta = fetch_patch(args.instance, args.change, args.revision)
        if not meta["tls_verified"]:
            print("警告：本次请求没有校验证书。", file=sys.stderr)
        sys.stdout.buffer.write(patch)
        return None
    if args.command == "resolve-commit":
        return resolve_commit(
            instance=args.instance,
            sha=args.sha,
            change_id=args.change_id,
            project=args.project,
            branch=args.branch,
            pick=args.pick,
        )
    raise GerritError("usage", f"未知子命令：{args.command}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _run(args)
    except GerritError as error:
        _emit(dict({"ok": False, "error": error.code, "message": error.message}, **error.extra))
        return 1
    if result is not None:
        _emit(dict({"ok": True}, **result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
