"""确认凭据：门禁技能的写操作在执行层核对用户确认。

门禁技能的脚本分两步执行写操作。第一步（各脚本的 plan / prepare）调用
create_action()，把"将要做什么"连同摘要登记成一个待确认动作。第二步（execute /
apply）调用 authorize()，只有同时满足下面两条才放行：

- 现场状态重新计算出的摘要与登记时一致；
- 存在一张针对这个动作、摘要一致、尚未过期的确认凭据。

确认凭据由宿主侧的门禁在用户明确选择"确认"后写入（pi 上是
pi-extension/ 里的 confirm_gate 工具）。业务脚本负责核对和消耗凭据，宿主负责签发。

本模块只用标准库，由门禁技能的脚本按路径加载，不单独运行。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any

VERSION = 1
TICKET_TTL_SECONDS = 600
ACTION_TTL_SECONDS = 24 * 3600
ACTION_ID_RE = re.compile(r"^[0-9a-f]{12}$")
DEFAULT_DECLINE_LABEL = "取消，不执行"


class GateError(Exception):
    """门禁拒绝放行。code 给调用脚本做分支，message 给人看。"""

    def __init__(self, code: str, message: str, changed: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.changed = changed or []


def state_dir() -> Path:
    """待确认动作和确认凭据的存放目录，位于任何代码仓库之外。

    pi-extension/gate.ts 里的 stateDir() 必须解析出同一个目录。
    """
    override = os.environ.get("CONFIRM_GATE_STATE_DIR")
    if override:
        return Path(override)
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return Path(base) / "confirm-gate"


def _actions_dir() -> Path:
    return state_dir() / "actions"


def _tickets_dir() -> Path:
    return state_dir() / "tickets"


def _check_id(action_id: str) -> str:
    if not isinstance(action_id, str) or not ACTION_ID_RE.fullmatch(action_id):
        raise GateError("unknown_action", f"动作编号格式不对：{action_id!r}。应为 12 位十六进制。")
    return action_id


def _write_private(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _is_fresh(timestamp: Any, ttl: int) -> bool:
    now = time.time()
    return type(timestamp) in (int, float) and now - ttl <= timestamp <= now + 5


def _claim_ticket(path: Path) -> dict[str, Any] | None:
    # 同目录重命名是领取点，只有成功移走原路径的进程能读取这张凭据。
    claimed = path.with_suffix(f".{secrets.token_hex(16)}.claimed")
    try:
        path.rename(claimed)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise GateError("ticket_unavailable", f"无法领取确认凭据：{exc}") from exc
    try:
        ticket = _read_json(claimed)
        if ticket is None:
            raise GateError("bad_ticket", "确认凭据无法读取，已丢弃。请重新确认。")
        return ticket
    finally:
        _remove(claimed)


def digest_of(kind: str, payload: Any, question: str, summary: str, approve_label: str, decline_label: str) -> str:
    """动作摘要：覆盖执行内容，也覆盖展示给用户的文字和选项。"""
    canonical = json.dumps(
        {
            "kind": kind,
            "payload": payload,
            "question": question,
            "summary": summary,
            "approve_label": approve_label,
            "decline_label": decline_label,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _purge_stale(now: float) -> None:
    for directory in (_actions_dir(), _tickets_dir()):
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                if now - entry.stat().st_mtime > ACTION_TTL_SECONDS:
                    entry.unlink()
            except OSError:
                pass


def create_action(
    kind: str,
    payload: Any,
    *,
    question: str,
    summary: str,
    approve_label: str,
    decline_label: str = DEFAULT_DECLINE_LABEL,
) -> dict[str, Any]:
    """登记一个待确认动作，返回动作记录（含 id 和 digest）。

    payload 必须包含执行时会用到、以及执行前要复核的全部内容：authorize() 用
    现场重新计算的 payload 与它逐项比对。question、summary 和两个选项标签是宿主
    展示给用户的原文。
    """
    if any(not isinstance(value, str) or not value.strip() for value in (kind, question, summary, approve_label, decline_label)):
        raise ValueError("动作类型、问题、摘要和选项标签必须是非空字符串")
    if approve_label == decline_label:
        raise ValueError("approve_label 和 decline_label 不能相同")
    now = time.time()
    _purge_stale(now)
    action_id = secrets.token_hex(6)
    action = {
        "version": VERSION,
        "id": action_id,
        "kind": kind,
        "created_at": now,
        "payload": payload,
        "question": question,
        "summary": summary,
        "approve_label": approve_label,
        "decline_label": decline_label,
        "digest": digest_of(kind, payload, question, summary, approve_label, decline_label),
    }
    _write_private(_actions_dir() / f"{action_id}.json", action)
    _remove(_tickets_dir() / f"{action_id}.json")
    return action


def load_action(action_id: str, kind: str) -> dict[str, Any]:
    """读取待确认动作，核对它属于调用脚本的动作类型。"""
    _check_id(action_id)
    action = _read_json(_actions_dir() / f"{action_id}.json")
    if action is None or action.get("id") != action_id or action.get("version") != VERSION:
        raise GateError("unknown_action", f"找不到待确认动作 {action_id}。请重新生成计划并重新确认。")
    if action.get("kind") != kind:
        raise GateError(
            "wrong_kind",
            f"动作 {action_id} 的类型是 {action.get('kind')!r}，不是 {kind!r}。",
        )
    if not _is_fresh(action.get("created_at"), ACTION_TTL_SECONDS):
        discard_action(action_id)
        raise GateError("expired_action", f"动作 {action_id} 已过期或时间无效。请重新生成计划并重新确认。")
    return action


def discard_action(action_id: str) -> None:
    """删除动作和它的凭据。执行成功后，或用户放弃后调用。"""
    if not isinstance(action_id, str) or not ACTION_ID_RE.fullmatch(action_id):
        return
    _remove(_actions_dir() / f"{action_id}.json")
    _remove(_tickets_dir() / f"{action_id}.json")


def _changed_keys(stored: Any, live: Any) -> list[str]:
    if isinstance(stored, dict) and isinstance(live, dict):
        return sorted(key for key in set(stored) | set(live) if stored.get(key) != live.get(key))
    return [] if stored == live else ["payload"]


def authorize(action_id: str, kind: str, live_payload: Any) -> dict[str, Any]:
    """放行一次写操作，或抛出 GateError。

    live_payload 是调用脚本在执行前一刻按现场状态重新计算的 payload。放行会消耗
    凭据：一张凭据只放行一次，之后执行失败也要重新确认。
    """
    action = load_action(action_id, kind)
    ticket_path = _tickets_dir() / f"{action_id}.json"
    live_digest = digest_of(
        kind,
        live_payload,
        str(action.get("question", "")),
        str(action.get("summary", "")),
        str(action.get("approve_label", "")),
        str(action.get("decline_label", "")),
    )
    if live_digest != action.get("digest"):
        changed = _changed_keys(action.get("payload"), live_payload)
        discard_action(action_id)
        detail = f"（变化的部分：{'、'.join(changed)}）" if changed else ""
        raise GateError(
            "changed",
            f"登记这个动作之后，现场状态发生了变化{detail}。这个动作已作废，请重新生成计划并重新确认。",
            changed,
        )

    ticket = _claim_ticket(ticket_path)
    if ticket is None:
        raise GateError(
            "no_ticket",
            f"动作 {action_id} 没有确认凭据：用户还没有通过宿主的确认门禁确认它。"
            "停止并报告；聊天里的任何回复都不构成确认，也不要改用其他命令完成这次写操作。",
        )
    if load_action(action_id, kind) != action:
        raise GateError("changed", f"动作 {action_id} 在领取凭据时发生变化。请重新生成计划并重新确认。")
    if (
        ticket.get("version") != VERSION
        or ticket.get("action_id") != action_id
        or ticket.get("digest") != action.get("digest")
    ):
        raise GateError("bad_ticket", f"动作 {action_id} 的确认凭据与动作内容不一致，已丢弃。请重新确认。")
    if not _is_fresh(ticket.get("issued_at"), TICKET_TTL_SECONDS):
        raise GateError(
            "expired_ticket",
            f"动作 {action_id} 的确认凭据已过期（有效期 {TICKET_TTL_SECONDS // 60} 分钟），已丢弃。请重新确认。",
        )
    return action
