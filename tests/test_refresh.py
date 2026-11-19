"""refresh-bu1-sdk-rules/scripts/refresh.py：在线读取、候选生成、门禁与原子替换。

覆盖场景：
- plan：全页面成功才生成候选；页面校验失败时 reference 与目录保持不变；
  sources_changed 强制正文草稿；候选临时文件在事务标记之后写入；动作 payload
  覆盖执行时会复核的全部内容；CRLF reference 不被换行归一化。
- apply：无凭据/过期凭据/错误动作号拒绝且不替换；现场 reference 或候选被改动后
  拒绝；两个 reference 都替换并复核成功后才清理标记；事务锁串行化并发。
- abort：双方都未替换时清理；已发生替换时拒绝清理。
- status：半更新状态的判定输出。
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from support import GateStateCase, load_script, run_main

refresh = load_script("refresh-bu1-sdk-rules", "refresh.py")
gate = load_script("confirm-gate", "gate.py")

KIND = refresh.KIND

GERRIT_RULES_V12_U = "2022-05-16T11:19:49Z"
GERRIT_DETAIL_V9_U = "2023-08-23T10:58:16Z"
REDMINE_V98_U = "2026-05-20T08:30:11Z"


def wiki_page(title, version, updated_on, text):
    return {"title": title, "text": text, "version": version, "updated_on": updated_on}


class FakeRedmineCli:
    """按页面标题回放 wiki_page JSON，记录调用参数。"""

    def __init__(self, pages, fail_titles=()):
        self.pages = dict(pages)
        self.fail_titles = set(fail_titles)
        self.calls = []

    def __call__(self, command, **kwargs):
        path_argument = command[command.index("get") + 1]
        title = next(name for name, encoded in refresh.PAGE_URL_PATH.items() if encoded in path_argument)
        self.calls.append({"path": path_argument, "command": list(command)})
        if title in self.fail_titles:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="模拟读取失败")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"ok": True, "data": {"wiki_page": self.pages[title]}}, ensure_ascii=False),
        )


def cli_pages(gerrit_version=12, detail_version=9, redmine_version=98, gerrit_text="提交前自测。", extra=""):
    return {
        "Gerrit使用规则": wiki_page("Gerrit使用规则", gerrit_version, GERRIT_RULES_V12_U, gerrit_text + extra),
        "Gerrit补丁生成细则": wiki_page("Gerrit补丁生成细则", detail_version, GERRIT_DETAIL_V9_U, "Type 后接 Redmine ID。"),
        "Redmine使用规则": wiki_page("Redmine使用规则", redmine_version, REDMINE_V98_U, "结论三要素。"),
    }


class RefreshCase(GateStateCase):
    """把仓库路径重定向到临时沙箱：以真实 reference 为夹具，不触碰真实树。"""

    def setUp(self):
        super().setUp()
        self.sandbox_repo = self.tmp / "repo"
        for snapshot, config in refresh.SNAPSHOTS.items():
            source = Path(load_source_reference(config["reference"]))
            target = self.sandbox_repo / config["reference"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        self.sandbox_skill = self.sandbox_repo / "refresh-bu1-sdk-rules"
        self.sandbox_skill.mkdir(parents=True, exist_ok=True)
        sandbox_cli = self.sandbox_repo / "redmine" / "scripts" / "redmine.py"
        sandbox_cli.parent.mkdir(parents=True, exist_ok=True)
        sandbox_cli.write_bytes(load_source_reference("redmine/scripts/redmine.py").read_bytes())
        for name, value in (
            ("REPO_ROOT", self.sandbox_repo),
            ("SKILL_DIR", self.sandbox_skill),
            ("PENDING_PATH", self.sandbox_skill / ".refresh.pending"),
            ("PENDING_LOCK_PATH", self.sandbox_skill / ".refresh.pending.lock"),
        ):
            patcher = mock.patch.object(refresh, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        cli_patcher = mock.patch.object(refresh.os, "environ", {**refresh.os.environ, "REDMINE_CLI": str(sandbox_cli)})
        cli_patcher.start()
        self.addCleanup(cli_patcher.stop)

    def use_cli(self, pages, fail_titles=()):
        fake = FakeRedmineCli(pages, fail_titles)
        patcher = mock.patch.object(refresh.subprocess, "run", side_effect=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    def exec_cmd(self, *argv):
        code, parsed, _stdout, _stderr = run_main(refresh, list(argv))
        return code, parsed

    def plan(self, *extra_args):
        return self.exec_cmd("plan", "--checked-by", "tester", *extra_args)

    def plan_succeeds(self, *extra_args):
        code, out = self.plan(*extra_args)
        self.assertEqual(code, 0, out)
        self.assertTrue(out["ok"], out)
        return out

    def apply_ok(self, out):
        self.approve(out["action_id"])
        code, result = self.exec_cmd("apply", "--action-id", out["action_id"])
        self.assertEqual(code, 0, result)
        self.assertTrue(result["ok"], result)
        return result

    # ---- 沙箱内的事实查询

    def ref_path(self, snapshot):
        return refresh.reference_path(snapshot)

    def ref_raw(self, snapshot):
        return self.ref_path(snapshot).read_bytes()

    def pending_data(self):
        return json.loads(refresh.PENDING_PATH.read_text(encoding="utf-8"))

    def temp_paths(self):
        found = []
        for config in refresh.SNAPSHOTS.values():
            found.extend(sorted((self.sandbox_repo / config["reference"]).parent.glob("*.tmp-*")))
        return found

    def temp_of(self, snapshot):
        return self.ref_path(snapshot).with_name(self.pending_data()["snapshots"][snapshot]["temp"])

    def assert_no_transaction(self):
        self.assertFalse(refresh.PENDING_PATH.exists())
        self.assertEqual(self.temp_paths(), [])


def load_source_reference(relative):
    from support import REPO_ROOT

    return REPO_ROOT / relative


class PlanTest(RefreshCase):
    def test_plan_calls_the_redmine_cli_get_endpoint_with_encoded_paths(self):
        fake = self.use_cli(cli_pages())
        out = self.plan_succeeds()
        shapes = {(call["command"][2], call["command"][3]) for call in fake.calls}
        self.assertEqual(len(fake.calls), 3)
        for command in fake.calls:
            self.assertTrue(command["command"][1].endswith("redmine.py"))
        self.assertEqual(
            {item[1] for item in shapes},
            {
                "projects/bu1-sdk/wiki/Gerrit%E4%BD%BF%E7%94%A8%E8%A7%84%E5%88%99.json",
                "projects/bu1-sdk/wiki/Gerrit%E8%A1%A5%E4%B8%81%E7%94%9F%E6%88%90%E7%BB%86%E5%88%99.json",
                "projects/bu1-sdk/wiki/Redmine%E4%BD%BF%E7%94%A8%E8%A7%84%E5%88%99.json",
            },
        )
        self.assertEqual({item[0] for item in shapes}, {"get"})

    def test_plan_refuses_when_gate_state_is_unusable(self):
        blocked = self.tmp / "blocked-gate"
        blocked.mkdir(mode=0o000)
        self.use_cli(cli_pages())
        env = dict(os.environ, CONFIRM_GATE_STATE_DIR=str(blocked))
        with mock.patch.dict(refresh.os.environ, env, clear=True):
            code, out = self.exec_cmd("plan", "--checked-by", "tester")
        self.assertEqual(code, 1)
        self.assertEqual(out["error"], "gate_unavailable")
        self.assert_no_transaction()

    def test_plan_writes_pending_then_candidates_and_registers_action(self):
        self.use_cli(cli_pages())
        out = self.plan_succeeds()
        self.assertRegex(out["action_id"], r"^[0-9a-f]{12}$")
        pending = self.pending_data()
        self.assertEqual(set(pending["snapshots"]), set(refresh.SNAPSHOTS))
        self.assertEqual(sorted(pending["pages"]), sorted(refresh.PAGE_URL_PATH))
        for snapshot, state in pending["snapshots"].items():
            temp = self.temp_of(snapshot)
            self.assertTrue(temp.is_file(), temp)
            self.assertEqual(temp.parent, self.ref_path(snapshot).parent)
            self.assertEqual(state["sha256_before"], refresh.sha256_bytes(self.ref_path(snapshot)))
            self.assertEqual(state["candidate_sha256"], refresh.sha256_bytes(temp))
        # 事务标记的创建时间早于候选临时文件：标记是第一个落盘的写入。
        self.assertLess(refresh.PENDING_PATH.stat().st_mtime_ns, min(p.stat().st_mtime_ns for p in self.temp_paths()))
        # 动作已登记，payload 覆盖执行时会复核的内容。
        stored = json.loads((self.state_dir / "actions" / f"{out['action_id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["kind"], KIND)
        self.assertEqual(stored["approve_label"], "确认刷新规则")
        self.assertEqual(stored["decline_label"], "保留现有快照")
        self.assertEqual(
            stored["payload"]["snapshots"]["commit-gerrit"]["candidate_sha256"],
            pending["snapshots"]["commit-gerrit"]["candidate_sha256"],
        )
        # 在线全文与差异（正文/元数据分开）供审阅。
        self.assertIn("提交前自测。", out["pages"]["Gerrit使用规则"]["text"])
        self.assertFalse(out["snapshots"]["commit-gerrit"]["diff"]["rules_changed"])
        self.assertTrue(out["snapshots"]["commit-gerrit"]["diff"]["metadata_changed"])

    def test_plan_preserves_crlf_reference_without_normalization(self):
        snapshot = "commit-gerrit"
        self.ref_path(snapshot).write_bytes(self.ref_raw(snapshot).replace(b"\n", b"\r\n"))
        self.use_cli(cli_pages())
        out = self.plan_succeeds()
        raw = self.temp_of(snapshot).read_bytes()
        self.assertIn(b"\r\n", raw)
        self.assertNotRegex(raw, rb"(?<!\r)\n")
        self.assertEqual(self.pending_data()["snapshots"][snapshot]["candidate_sha256"], refresh.sha256_bytes(self.temp_of(snapshot)))
        self.assertEqual(self.pending_data()["snapshots"][snapshot]["sha256_before"], refresh.sha256_bytes(self.ref_path(snapshot)))
        stored = json.loads((self.state_dir / "actions" / f"{out['action_id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["payload"]["snapshots"][snapshot]["candidate_sha256"], refresh.sha256_bytes(self.temp_of(snapshot)))

    def test_plan_fails_when_any_page_fails_and_keeps_everything(self):
        for broken in cli_pages():
            with self.subTest(broken=broken):
                self.use_cli(cli_pages(), fail_titles=[broken])
                code, out = self.plan()
                self.assertEqual(code, 1)
                self.assertFalse(out["ok"])
                self.assertEqual(out["error"], "fetch_failed")
                self.assert_no_transaction()
                self.assertIn("source_version: Gerrit使用规则=12".encode(), self.ref_raw("commit-gerrit"))

    def test_plan_fails_on_invalid_page_payload(self):
        bad_pages = [
            ("空 text", dict(cli_pages(), **{"Redmine使用规则": wiki_page("Redmine使用规则", 98, REDMINE_V98_U, "")})),
            ("version 非正整数", dict(cli_pages(), **{"Redmine使用规则": wiki_page("Redmine使用规则", 0, REDMINE_V98_U, "正文")})),
            ("updated_on 不可解析", dict(cli_pages(), **{"Redmine使用规则": wiki_page("Redmine使用规则", 98, "not-a-time", "正文")})),
            ("updated_on 缺时区", dict(cli_pages(), **{"Redmine使用规则": wiki_page("Redmine使用规则", 98, "2026-05-20T08:30:11", "正文")})),
            ("updated_on 非 UTC 时区", dict(cli_pages(), **{"Redmine使用规则": wiki_page("Redmine使用规则", 98, "2026-05-20T16:30:11+08:00", "正文")})),
        ]
        for label, pages in bad_pages:
            with self.subTest(label=label):
                self.use_cli(pages)
                code, out = self.plan()
                self.assertEqual(code, 1)
                self.assertEqual(out["error"], "bad_page")
                self.assert_no_transaction()

    def test_plan_stops_on_sources_changed_without_body_draft(self):
        self.use_cli(cli_pages(gerrit_version=13))
        code, out = self.plan()
        self.assertEqual(code, 1)
        self.assertEqual(out["error"], "sources_changed")
        self.assertEqual(out["missing_drafts"], {"commit-gerrit": {"Gerrit使用规则": {"local": 12, "online": 13}}})
        self.assertEqual(out["changed_sources"], out["missing_drafts"])
        # 诊断自带全部来源页面的在线全文，足以支撑正文草稿的审阅。
        self.assertEqual(sorted(out["online_pages"]), sorted(refresh.PAGE_URL_PATH))
        for page in out["online_pages"].values():
            self.assertIn("text", page)
        self.assert_no_transaction()

    def test_plan_accepts_reviewed_body_draft_when_sources_changed(self):
        self.use_cli(cli_pages(gerrit_version=13, gerrit_text="新的在线全文，含新规则。"))
        draft = self.tmp / "draft.md"
        original = self.ref_raw("commit-gerrit")
        draft.write_bytes(original.replace("## 公版 Gerrit 流程".encode(), "## 公版 Gerrit 流程（已审阅修订）".encode()))
        out = self.plan_succeeds("--body-draft", f"commit-gerrit={draft}")
        self.assertTrue(out["changed_sources"])
        self.assertEqual(out["snapshots"]["commit-gerrit"]["body_draft"], str(draft))
        self.assertTrue(out["snapshots"]["commit-gerrit"]["diff"]["rules_changed"])
        candidate = self.temp_of("commit-gerrit").read_text(encoding="utf-8")
        self.assertIn("## 公版 Gerrit 流程（已审阅修订）", candidate)
        self.assertIn("source_version: Gerrit使用规则=13", candidate)
        # 另一个快照不受草稿影响，仍走原 reference + 元数据刷新。
        other = self.temp_of("update-issue-conclusion").read_text(encoding="utf-8")
        self.assertIn("source_version: 98", other)
        # 无 mkstemp 残片。
        self.assertEqual([p for p in self.temp_paths() if p.name.endswith(".tmp")], [])

    def test_plan_collects_every_snapshot_missing_a_draft_in_one_diagnostic(self):
        self.use_cli(cli_pages(gerrit_version=13, redmine_version=99))
        code, out = self.plan()
        self.assertEqual(code, 1)
        self.assertEqual(out["error"], "sources_changed")
        # 一次诊断同时列出两个缺草稿的快照，而不是只报第一个。
        self.assertEqual(sorted(out["missing_drafts"]), ["commit-gerrit", "update-issue-conclusion"])
        self.assertEqual(sorted(out["online_pages"]), sorted(refresh.PAGE_URL_PATH))
        self.assert_no_transaction()

    def test_plan_sha256_before_binds_read_time_bytes_and_apply_catches_concurrent_edit(self):
        self.use_cli(cli_pages())
        concurrent_line = "\n并发编辑：fetch 期间有人改了规则文件。\n"

        def fetch_and_edit(title, url):
            if title == next(iter(refresh.PAGE_URL_PATH)):
                self.ref_path("commit-gerrit").write_bytes(self.ref_raw("commit-gerrit") + concurrent_line.encode())
            return refresh.__dict__["_fetch_stub"](title, url)

        refresh._fetch_stub = refresh.fetch_page
        with mock.patch.object(refresh, "fetch_page", side_effect=fetch_and_edit):
            out = self.plan_succeeds()
        pending = self.pending_data()
        # 登记的替换前哈希绑定读取时的字节，不含并发编辑。
        self.assertNotEqual(
            pending["snapshots"]["commit-gerrit"]["sha256_before"], refresh.sha256_bytes(self.ref_path("commit-gerrit"))
        )
        self.approve(out["action_id"])
        code, result = self.exec_cmd("apply", "--action-id", out["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(result["error"], "gate_changed")
        # 并发编辑未被静默覆盖。
        self.assertIn(concurrent_line.encode(), self.ref_raw("commit-gerrit"))

    def test_plan_cleanup_on_action_failure_removes_temp_and_marker(self):
        self.use_cli(cli_pages())

        class ExplodingGate:
            def state_dir(self):
                return gate.state_dir()

            def create_action(self, *args, **kwargs):
                raise OSError("登记失败")

        with mock.patch.object(refresh, "_load_gate", return_value=ExplodingGate()):
            with self.assertRaises(OSError):
                refresh.main(["plan", "--checked-by", "tester"])
        # 登记动作失败时清理路径正确（无 KeyError），临时文件和标记都被删除。
        self.assert_no_transaction()

    def test_plan_refuses_pending_transaction(self):
        self.use_cli(cli_pages())
        self.plan_succeeds()
        code, second = self.plan()
        self.assertEqual(code, 1)
        self.assertEqual(second["error"], "interrupted")
        self.assertTrue(refresh.PENDING_PATH.exists())
        self.assertEqual(len(self.temp_paths()), 2)

    def test_diff_body_vs_metadata(self):
        before = "# R\n\n- `source_version: 1`\n\n## 正文\n\n旧规则\n"
        only_meta = "# R\n\n- `source_version: 2`\n\n## 正文\n\n旧规则\n"
        with_body = "# R\n\n- `source_version: 2`\n\n## 正文\n\n新规则\n"
        self.assertFalse(refresh.diff_snapshot(before, only_meta)["rules_changed"])
        self.assertTrue(refresh.diff_snapshot(before, only_meta)["metadata_changed"])
        self.assertTrue(refresh.diff_snapshot(before, with_body)["rules_changed"])


class ApplyTest(RefreshCase):
    def test_apply_replaces_both_and_cleans_transaction(self):
        self.use_cli(cli_pages())
        out = self.plan_succeeds()
        result = self.apply_ok(out)
        self.assertEqual(result["replaced"], list(refresh.SNAPSHOTS))
        self.assertIsNone(result["pending"])
        self.assertIsNone(result["cleanup_failures"])
        self.assert_no_transaction()
        gerrit = self.ref_path("commit-gerrit").read_text(encoding="utf-8")
        self.assertIn("source_version: Gerrit使用规则=12; Gerrit补丁生成细则=9", gerrit)
        self.assertIn(f"source_updated_on: Gerrit使用规则={GERRIT_RULES_V12_U}", gerrit)
        self.assertEqual(refresh.current_metadata(gerrit)["checked_by"], "tester")
        redmine = self.ref_path("update-issue-conclusion").read_text(encoding="utf-8")
        self.assertIn("source_version: 98", redmine)
        self.assertEqual(refresh.current_metadata(redmine)["checked_by"], "tester")

    def test_apply_without_ticket_refuses_and_keeps_everything(self):
        self.use_cli(cli_pages())
        out = self.plan_succeeds()
        before = {s: refresh.sha256_bytes(self.ref_path(s)) for s in refresh.SNAPSHOTS}
        code, result = self.exec_cmd("apply", "--action-id", out["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(result["error"], "gate_no_ticket")
        for snapshot in refresh.SNAPSHOTS:
            self.assertEqual(refresh.sha256_bytes(self.ref_path(snapshot)), before[snapshot])
        self.assertTrue(refresh.PENDING_PATH.exists())
        self.assertEqual(len(self.temp_paths()), 2)

    def test_apply_refuses_expired_ticket(self):
        self.use_cli(cli_pages())
        out = self.plan_succeeds()
        self.approve(out["action_id"], issued_at=time.time() - gate.TICKET_TTL_SECONDS - 1)
        code, result = self.exec_cmd("apply", "--action-id", out["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(result["error"], "gate_expired_ticket")
        self.assertTrue(refresh.PENDING_PATH.exists())
        self.assertEqual(len(self.temp_paths()), 2)

    def test_apply_refuses_when_reference_changed_after_plan(self):
        self.use_cli(cli_pages())
        out = self.plan_succeeds()
        original = self.ref_raw("update-issue-conclusion")
        self.ref_path("update-issue-conclusion").write_bytes(original + "\n外部改动\n".encode())
        self.approve(out["action_id"])
        code, result = self.exec_cmd("apply", "--action-id", out["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(result["error"], "gate_changed")
        self.assertEqual(result.get("changed"), ["snapshots"])
        self.assertTrue(refresh.PENDING_PATH.exists())
        self.assertIn("\n外部改动\n".encode(), self.ref_raw("update-issue-conclusion"))

    def test_apply_refuses_when_candidate_tampered(self):
        self.use_cli(cli_pages())
        out = self.plan_succeeds()
        self.temp_of("commit-gerrit").write_bytes(b"tampered")
        self.approve(out["action_id"])
        code, result = self.exec_cmd("apply", "--action-id", out["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(result["error"], "gate_changed")
        self.assertTrue(refresh.PENDING_PATH.exists())
        for snapshot in refresh.SNAPSHOTS:
            self.assertEqual(
                refresh.sha256_bytes(self.ref_path(snapshot)),
                self.pending_data()["snapshots"][snapshot]["sha256_before"],
            )

    def test_apply_refuses_wrong_action_id(self):
        self.use_cli(cli_pages())
        out = self.plan_succeeds()
        self.approve(out["action_id"])
        code, result = self.exec_cmd("apply", "--action-id", "0123456789ab")
        self.assertEqual(code, 1)
        self.assertEqual(result["error"], "gate_unknown_action")
        self.assertTrue(refresh.PENDING_PATH.exists())

    def test_apply_requires_a_transaction(self):
        code, result = self.exec_cmd("apply", "--action-id", "0123456789ab")
        self.assertEqual(code, 1)
        self.assertEqual(result["error"], "no_transaction")

    def test_apply_is_serialized_by_the_transaction_lock(self):
        self.use_cli(cli_pages())
        out = self.plan_succeeds()
        self.approve(out["action_id"])
        holder = open(refresh.PENDING_LOCK_PATH, "a+")
        self.addCleanup(holder.close)
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
        try:
            code, result = self.exec_cmd("apply", "--action-id", out["action_id"])
        finally:
            fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
        self.assertEqual(code, 1)
        self.assertEqual(result["error"], "busy")
        self.assertTrue(refresh.PENDING_PATH.exists())
        self.assertEqual(len(self.temp_paths()), 2)
        # 锁释放后可以正常完成。
        result = self.apply_ok(out)
        self.assertEqual(result["replaced"], list(refresh.SNAPSHOTS))
        self.assert_no_transaction()

    def test_apply_failure_keeps_marker_with_replaced_records(self):
        self.use_cli(cli_pages())
        out = self.plan_succeeds()
        pending_before = self.pending_data()
        # 破坏第二个候选，使 authorize 在现场重算时即失败。
        self.temp_of("update-issue-conclusion").write_bytes(b"tampered")
        self.approve(out["action_id"])
        code, result = self.exec_cmd("apply", "--action-id", out["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(result["error"], "gate_changed")
        for snapshot in refresh.SNAPSHOTS:
            self.assertEqual(
                refresh.sha256_bytes(self.ref_path(snapshot)),
                pending_before["snapshots"][snapshot]["sha256_before"],
            )
        code, status = self.exec_cmd("status")
        self.assertTrue(status["ok"])
        self.assertTrue(all(not value["already_replaced"] for value in status["snapshots"].values()))

    def test_apply_rechecks_each_target_bytes_right_before_its_own_replace(self):
        self.use_cli(cli_pages())
        out = self.plan_succeeds()
        self.approve(out["action_id"])
        second = self.ref_path("update-issue-conclusion")
        tampered = b"mid-refresh tampering\n"
        real_replace = refresh.os.replace

        def replace_then_tamper_second(src, dst):
            real_replace(src, dst)
            if str(dst).endswith("bu1-sdk-gerrit-rules.md"):
                second.write_bytes(tampered)

        with mock.patch.object(refresh.os, "replace", side_effect=replace_then_tamper_second):
            code, result = self.exec_cmd("apply", "--action-id", out["action_id"])
        # 第二个目标在它自己的替换前一刻复核失败：不再替换，事务保留并记录已替换项。
        self.assertEqual(code, 1)
        self.assertEqual(result["error"], "changed_state")
        self.assertEqual(result["snapshot"], "update-issue-conclusion")
        self.assertEqual(self.ref_raw("update-issue-conclusion"), tampered)
        pending = self.pending_data()
        self.assertEqual(pending["replaced"], ["commit-gerrit"])
        self.assertEqual(
            refresh.sha256_bytes(self.ref_path("commit-gerrit")),
            pending["snapshots"]["commit-gerrit"]["candidate_sha256"],
        )

    def test_apply_survives_unexpected_error_midway_reports_replaced(self):
        self.use_cli(cli_pages())
        out = self.plan_succeeds()
        self.approve(out["action_id"])
        # 第二个替换执行时抛出非 RefreshError 异常，模拟进程级故障路径。
        real_replace = refresh.os.replace

        def flaky(src, dst):
            if str(dst).endswith("bu1-sdk-conclusion-rules.md"):
                raise OSError("模拟替换中断")
            return real_replace(src, dst)

        with mock.patch.object(refresh.os, "replace", side_effect=flaky):
            code, result = self.exec_cmd("apply", "--action-id", out["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(result["error"], "replace_failed")
        self.assertEqual(result["replaced"], ["commit-gerrit"])
        pending_after = self.pending_data()
        self.assertEqual(pending_after["replaced"], ["commit-gerrit"])
        # 第一个 reference 已是候选内容，第二个保持原样：半更新可见、可判定。
        self.assertEqual(
            refresh.sha256_bytes(self.ref_path("commit-gerrit")),
            pending_after["snapshots"]["commit-gerrit"]["candidate_sha256"],
        )
        self.assertEqual(
            refresh.sha256_bytes(self.ref_path("update-issue-conclusion")),
            pending_after["snapshots"]["update-issue-conclusion"]["sha256_before"],
        )
        code, status = self.exec_cmd("status")
        self.assertTrue(status["snapshots"]["commit-gerrit"]["already_replaced"])
        self.assertTrue(status["snapshots"]["update-issue-conclusion"]["untouched"])
        # 半更新后 abort 拒绝清理，指向人工恢复。
        code, aborted = self.exec_cmd("abort")
        self.assertEqual(code, 1)
        self.assertEqual(aborted["error"], "already_replaced")
        self.assertTrue(refresh.PENDING_PATH.exists())


class AbortStatusTest(RefreshCase):
    def test_abort_without_transaction(self):
        code, result = self.exec_cmd("abort")
        self.assertEqual(code, 0)
        self.assertIsNone(result["pending"])

    def test_abort_cleans_when_neither_replaced(self):
        self.use_cli(cli_pages())
        out = self.plan_succeeds()
        before = {s: refresh.sha256_bytes(self.ref_path(s)) for s in refresh.SNAPSHOTS}
        code, result = self.exec_cmd("abort")
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assert_no_transaction()
        for snapshot in refresh.SNAPSHOTS:
            self.assertEqual(refresh.sha256_bytes(self.ref_path(snapshot)), before[snapshot])

    def test_abort_refuses_when_reference_replaced(self):
        self.use_cli(cli_pages())
        out = self.plan_succeeds()
        pending = self.pending_data()
        refresh.os.replace(self.temp_of("commit-gerrit"), self.ref_path("commit-gerrit"))
        code, result = self.exec_cmd("abort")
        self.assertEqual(code, 1)
        self.assertEqual(result["error"], "already_replaced")
        self.assertTrue(refresh.PENDING_PATH.exists())

    def test_abort_refuses_when_reference_modified_outside(self):
        self.use_cli(cli_pages())
        self.plan_succeeds()
        self.ref_path("commit-gerrit").write_bytes("外部改动".encode())
        code, result = self.exec_cmd("abort")
        self.assertEqual(code, 1)
        self.assertEqual(result["error"], "not_clean")
        self.assertTrue(refresh.PENDING_PATH.exists())

    def test_status_reports_half_replaced_state(self):
        self.use_cli(cli_pages())
        self.plan_succeeds()
        refresh.os.replace(self.temp_of("commit-gerrit"), self.ref_path("commit-gerrit"))
        code, status = self.exec_cmd("status")
        self.assertEqual(code, 0)
        self.assertTrue(status["snapshots"]["commit-gerrit"]["already_replaced"])
        self.assertFalse(status["snapshots"]["commit-gerrit"]["untouched"])
        self.assertTrue(status["snapshots"]["update-issue-conclusion"]["untouched"])
        self.assertTrue(status["snapshots"]["update-issue-conclusion"]["temp_file_exists"])

    def test_status_without_pending(self):
        code, status = self.exec_cmd("status")
        self.assertEqual(code, 0)
        self.assertIsNone(status["pending"])
        for snapshot in refresh.SNAPSHOTS:
            self.assertTrue(status["snapshots"][snapshot]["exists"])


if __name__ == "__main__":
    unittest.main()
