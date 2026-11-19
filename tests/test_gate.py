"""confirm-gate/scripts/gate.py：待确认动作与确认凭据。"""

from __future__ import annotations

import json
import multiprocessing
import os
import time
import unittest

from support import GateStateCase, issue_ticket, load_script

KIND = "demo-write"


def authorize_together(action, barrier, results):
    gate = load_script("confirm-gate", "gate.py")
    barrier.wait(timeout=10)
    try:
        gate.authorize(action["id"], action["kind"], action["payload"])
        results.put("authorized")
    except gate.GateError as error:
        results.put(error.code)

class GateTest(GateStateCase):
    def make(self, payload=None, **overrides):
        options = {"question": "是否执行？", "summary": "摘要第一行\n摘要第二行", "approve_label": "确认执行"}
        options.update(overrides)
        return self.gate.create_action(KIND, payload if payload is not None else {"a": 1, "b": "值"}, **options)

    def assert_refused(self, code, action_id, payload, kind=KIND):
        with self.assertRaises(self.gate.GateError) as caught:
            self.gate.authorize(action_id, kind, payload)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_create_action_records_what_the_user_will_see(self):
        action = self.make()
        self.assertRegex(action["id"], r"^[0-9a-f]{12}$")
        stored = json.loads((self.state_dir / "actions" / f"{action['id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(stored, action)
        self.assertEqual(stored["decline_label"], "取消，不执行")
        self.assertEqual(os.stat(self.state_dir / "actions" / f"{action['id']}.json").st_mode & 0o777, 0o600)

    def test_action_with_no_visible_summary_is_refused(self):
        with self.assertRaises(ValueError):
            self.make(summary=" ")
        self.assertFalse((self.state_dir / "actions").exists())

    def test_identical_labels_are_rejected(self):
        with self.assertRaises(ValueError):
            self.make(approve_label="同一个", decline_label="同一个")

    def test_authorize_without_ticket_is_refused_and_keeps_the_action(self):
        action = self.make()
        self.assert_refused("no_ticket", action["id"], {"a": 1, "b": "值"})
        self.assertTrue((self.state_dir / "actions" / f"{action['id']}.json").exists())

    def test_ticket_authorizes_exactly_once(self):
        action = self.make()
        issue_ticket(self.state_dir, action)
        returned = self.gate.authorize(action["id"], KIND, {"a": 1, "b": "值"})
        self.assertEqual(returned["digest"], action["digest"])
        self.assert_refused("no_ticket", action["id"], {"a": 1, "b": "值"})

    def test_concurrent_processes_can_only_claim_a_ticket_once(self):
        context = multiprocessing.get_context("spawn")
        results = context.Queue()
        self.addCleanup(results.close)
        action = self.make()
        issue_ticket(self.state_dir, action)
        count = 12
        barrier = context.Barrier(count)
        workers = [
            context.Process(target=authorize_together, args=(action, barrier, results))
            for _ in range(count)
        ]
        try:
            for worker in workers:
                worker.start()
            outcomes = [results.get(timeout=15) for _ in workers]
        finally:
            for worker in workers:
                if worker.pid is None:
                    continue
                if worker.is_alive():
                    worker.terminate()
                worker.join(timeout=5)
        self.assertCountEqual(outcomes, ["authorized"] + ["no_ticket"] * (count - 1))

    def test_changed_state_voids_the_action_even_with_a_ticket(self):
        action = self.make()
        issue_ticket(self.state_dir, action)
        error = self.assert_refused("changed", action["id"], {"a": 2, "b": "值"})
        self.assertEqual(error.changed, ["a"])
        self.assertFalse((self.state_dir / "actions" / f"{action['id']}.json").exists())
        self.assertFalse((self.state_dir / "tickets" / f"{action['id']}.json").exists())
        self.assert_refused("unknown_action", action["id"], {"a": 1, "b": "值"})

    def test_ticket_for_other_content_is_refused(self):
        action = self.make()
        issue_ticket(self.state_dir, dict(action, digest="0" * 64))
        self.assert_refused("bad_ticket", action["id"], {"a": 1, "b": "值"})
        self.assert_refused("no_ticket", action["id"], {"a": 1, "b": "值"})

    def test_ticket_of_another_action_is_refused(self):
        first, second = self.make(), self.make()
        path = issue_ticket(self.state_dir, first)
        path.rename(self.state_dir / "tickets" / f"{second['id']}.json")
        self.assert_refused("bad_ticket", second["id"], {"a": 1, "b": "值"})

    def test_expired_ticket_is_refused(self):
        action = self.make()
        issue_ticket(self.state_dir, action, issued_at=time.time() - self.gate.TICKET_TTL_SECONDS - 1)
        self.assert_refused("expired_ticket", action["id"], {"a": 1, "b": "值"})

    def test_expired_or_invalid_action_is_refused_even_with_a_fresh_ticket(self):
        for created_at in (time.time() - self.gate.ACTION_TTL_SECONDS - 1, float("nan"), "now", None):
            action = self.make()
            issue_ticket(self.state_dir, action)
            path = self.state_dir / "actions" / f"{action['id']}.json"
            path.write_text(json.dumps(dict(action, created_at=created_at)), encoding="utf-8")
            self.assert_refused("expired_action", action["id"], {"a": 1, "b": "值"})
            self.assertFalse((self.state_dir / "tickets" / path.name).exists())

    def test_ticket_from_the_future_or_without_time_is_refused(self):
        for issued_at in (time.time() + 3600, "now", True, float("nan"), float("inf"), 10**350):
            action = self.make()
            path = issue_ticket(self.state_dir, action)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["issued_at"] = issued_at
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assert_refused("expired_ticket", action["id"], {"a": 1, "b": "值"})

    def test_edited_summary_after_approval_is_refused(self):
        action = self.make()
        issue_ticket(self.state_dir, action)
        path = self.state_dir / "actions" / f"{action['id']}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["summary"] = "被改过的摘要"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assert_refused("changed", action["id"], {"a": 1, "b": "值"})

    def test_wrong_kind_and_bad_ids_are_refused(self):
        action = self.make()
        issue_ticket(self.state_dir, action)
        self.assert_refused("wrong_kind", action["id"], {"a": 1, "b": "值"}, kind="other-kind")
        for bad in ("", "../../etc/x", "ABCDEF012345", "0123", action["id"] + "\n", None):
            self.assert_refused("unknown_action", bad, {})

    def test_creating_an_action_drops_a_leftover_ticket_for_the_same_id(self):
        action = self.make()
        issue_ticket(self.state_dir, action)
        with unittest.mock.patch.object(self.gate.secrets, "token_hex", return_value=action["id"]):
            again = self.make(payload={"a": 9})
        self.assertEqual(again["id"], action["id"])
        self.assert_refused("no_ticket", again["id"], {"a": 9})

    def test_stale_actions_are_purged_on_create(self):
        old = self.make()
        path = self.state_dir / "actions" / f"{old['id']}.json"
        stale = time.time() - self.gate.ACTION_TTL_SECONDS - 60
        os.utime(path, (stale, stale))
        self.make()
        self.assertFalse(path.exists())

    def test_discard_removes_action_and_ticket(self):
        action = self.make()
        issue_ticket(self.state_dir, action)
        self.gate.discard_action(action["id"])
        self.assertEqual(list((self.state_dir / "actions").iterdir()), [])
        self.assertEqual(list((self.state_dir / "tickets").iterdir()), [])
        self.gate.discard_action("not-an-id")

    def test_state_dir_resolution(self):
        with unittest.mock.patch.dict(os.environ, {"XDG_STATE_HOME": "/x/state"}, clear=False):
            os.environ.pop("CONFIRM_GATE_STATE_DIR")
            self.assertEqual(str(self.gate.state_dir()), "/x/state/confirm-gate")
            os.environ.pop("XDG_STATE_HOME")
            self.assertEqual(
                str(self.gate.state_dir()), os.path.join(os.path.expanduser("~"), ".local", "state", "confirm-gate")
            )

    def test_module_offers_no_way_to_issue_a_ticket(self):
        public = [name for name in dir(self.gate) if not name.startswith("_")]
        self.assertFalse([name for name in public if "issue" in name.lower() or "approve" in name.lower()], public)


if __name__ == "__main__":
    unittest.main()
