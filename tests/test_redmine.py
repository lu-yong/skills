"""redmine/scripts/redmine.py：凭据、分页、结论字段发现与两步回写。"""

from __future__ import annotations

import io
import json
import time
import unittest
import urllib.error
from urllib.parse import parse_qs, urlsplit
from unittest import mock

from support import GateStateCase, load_script, run_main

redmine = load_script("redmine", "redmine.py")

ISSUE_ID = "434931"
OTHER_ID = "434932"
CONCLUSION = "* 问题原因：x\n* 处理方案：y\n* 影响范围：z\n* 修改补丁：{{patch(12345)}}"
BASE = "https://redmine.example.invalid"


class Response:
    def __init__(self, payload, status=200):
        self._body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.status = status

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def issue(number=int(ISSUE_ID), conclusion="旧结论", tracker="错误", project="bu1-sdk"):
    return {
        "id": number,
        "subject": f"问题 {number}",
        "project": {"id": 7, "identifier": project},
        "tracker": {"id": 1, "name": tracker},
        "status": {"name": "进行中"},
        "updated_on": "2026-08-10T10:00:00Z",
        "custom_fields": [
            {"id": 9, "name": "结论", "value": conclusion},
            {"id": 5, "name": "问题性质", "value": "历史遗留"},
        ],
        "journals": [],
    }


def _respond(result) -> Response:
    if isinstance(result, Response):
        return result
    if isinstance(result, tuple):
        return Response(result[0], status=result[1])
    return Response(result)


class FakeRedmine:
    """按 method+path 回放/记录请求；issue 存在 self.issues 里，PUT 真改状态。"""

    def __init__(self, issues=None):
        self.issues = {str(item["id"]): item for item in issues or [issue()]}
        self.routes = {}
        self.calls = []
        self.put_bodies = []

    def route(self, method, path, handler):
        self.routes[f"{method} {path}"] = handler
        return self

    def __call__(self, request, timeout):
        split = urlsplit(request.full_url)
        call = {
            "method": request.get_method(),
            "url": request.full_url,
            "path": split.path,
            "params": parse_qs(split.query),
            "headers": dict(request.header_items()),
            "body": request.data.decode("utf-8") if request.data else None,
        }
        self.calls.append(call)
        handler = self.routes.get(f"{call['method']} {call['path']}")
        if handler is None:
            raise AssertionError(f"FakeRedmine 没有登记这个请求：{call['method']} {call['path']} {call['params']}")
        return _respond(handler(call["params"], call) if callable(handler) else handler)

    # 常用路由的便捷装法 -------------------------------------------------

    def serve_issue(self, number=ISSUE_ID):
        return self.route("GET", f"/issues/{number}.json", lambda params, call: {"issue": self.issues[str(number)]})

    def serve_put_issue(self, number=ISSUE_ID, inert=False):
        """inert=True 模拟服务器 204 却什么都没落库的读回不一致。"""

        def handler(params, call):
            self.put_bodies.append(json.loads(call["body"]))
            payload = self.put_bodies[-1]["issue"]
            if inert:
                return None, 204
            target = self.issues[str(number)]
            for field in payload.get("custom_fields", []):
                for existing in target["custom_fields"]:
                    if existing["id"] == field["id"]:
                        existing["value"] = field["value"]
            if "notes" in payload:
                target["journals"].append({"notes": payload["notes"]})
            target["updated_on"] = "2026-08-10T12:00:00Z"
            return None, 204

        return self.route("PUT", f"/issues/{number}.json", handler)


class RedmineCase(GateStateCase):
    def setUp(self):
        super().setUp()
        self.secret = self.write(self.tmp / "secret" / "SECRET.md", "# 注释\n\nAPI_KEY=test-key-123\n")
        self.patch_env({"REDMINE_SECRET_FILE": str(self.secret), "REDMINE_URL": BASE})
        self.server = self.use(FakeRedmine())
        self.server.serve_issue().serve_put_issue()

    def patch_env(self, extra):
        patcher = mock.patch.dict(redmine.os.environ, extra)
        patcher.start()
        self.addCleanup(patcher.stop)

    def use(self, server):
        patcher = mock.patch.object(redmine, "_urlopen", server)
        patcher.start()
        self.addCleanup(patcher.stop)
        return server

    def plan(self, conclusion=CONCLUSION, issue_id=ISSUE_ID):
        code, out, _, _ = run_main(redmine, ["plan-conclusion", issue_id, "--conclusion", conclusion])
        return code, out

    def apply(self, action_id):
        code, out, _, _ = run_main(redmine, ["apply-conclusion", "--action-id", action_id])
        return code, out

    def action_path(self, action_id):
        return self.state_dir / "actions" / f"{action_id}.json"

    def action_ids(self):
        return [path.stem for path in (self.state_dir / "actions").glob("*.json")] if (self.state_dir / "actions").is_dir() else []

    def ticket_path(self, action_id):
        return self.state_dir / "tickets" / f"{action_id}.json"

    def calls(self, method, path=None):
        return [call for call in self.server.calls if call["method"] == method and (path is None or call["path"] == path)]


class CredentialTest(RedmineCase):
    def test_header_auth_only_and_key_never_in_url_or_output(self):
        self.server.route("GET", "/users/current.json", {"user": {"id": 3, "login": "luyong", "admin": False}})
        code, out, stdout, _ = run_main(redmine, ["whoami"])
        self.assertEqual((code, out["ok"], out["user"]["login"]), (0, True, "luyong"))
        call = self.server.calls[0]
        self.assertEqual(call["headers"].get("X-redmine-api-key"), "test-key-123")
        self.assertIsNone(call["headers"].get("Content-type"))
        self.assertNotIn("test-key-123", call["url"])
        self.assertNotIn("key=", call["url"])
        self.assertNotIn("test-key-123", stdout)

    def test_secret_file_rules(self):
        for text, expected in (
            ("# 标题\nAPI_KEY=abc\n", "abc"),
            ("API_KEY=abc=def\n", "abc=def"),
            ("\nAPI_KEY=  spaced  \n", "spaced"),
        ):
            self.secret.write_text(text, encoding="utf-8")
            self.assertEqual(redmine.read_api_key(), expected, text)
        for text in ("", "# 只有注释\n", "API_KEY=\n", "API_KEY=a\nAPI_KEY=b\n", "APIKEY=x\n", "API_KEY=不是ASCII\n"):
            self.secret.write_text(text, encoding="utf-8")
            with self.assertRaises(redmine.RedmineError) as caught:
                redmine.read_api_key()
            self.assertIn(caught.exception.code, ("bad_secret", "no_credentials"), text)

    def test_missing_secret_and_bad_issue_id(self):
        self.secret.unlink()
        code, out, _, _ = run_main(redmine, ["whoami"])
        self.assertEqual((code, out["error"]), (1, "no_credentials"))
        for bad in ("0", "#12", "12,13", " 12", "12x"):
            code, out, _, _ = run_main(redmine, ["issue", bad])
            self.assertEqual(out["error"], "bad_issue_id", bad)
        self.assertEqual(self.server.calls, [])

    def test_url_must_be_a_bare_http_address(self):
        for url in ("https://user:pw@host/redmine", "https://host/redmine?x=1", "https://host/redmine#f", "ftp://host", "host/redmine"):
            self.patch_env({"REDMINE_URL": url})
            code, out, _, _ = run_main(redmine, ["whoami"])
            self.assertEqual((code, out["error"]), (1, "bad_url"), url)
        self.assertEqual(self.server.calls, [])

    def test_redirect_response_is_refused_not_followed(self):
        self.server.route("GET", "/users/current.json", lambda params, call: Response(b"", 302))
        code, out, _, _ = run_main(redmine, ["whoami"])
        self.assertEqual((code, out["error"], out["http_status"]), (1, "http", 302))
        self.assertEqual(len(self.server.calls), 1)

    def test_http_network_and_query_key_errors(self):
        def raise_401(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 401, "Denied", {}, io.BytesIO(b"denied: test-key-123"))

        def raise_network(request, timeout):
            raise urllib.error.URLError("refused")

        with mock.patch.object(redmine, "_urlopen", raise_401):
            code, out, stdout, _ = run_main(redmine, ["whoami"])
            self.assertEqual((code, out["error"], out["http_status"]), (1, "auth", 401))
            self.assertNotIn("test-key-123", stdout)
            self.assertNotIn("test-key-123", out["message"])  # 服务器回显密钥时按密文脱敏
        with mock.patch.object(redmine, "_urlopen", raise_network):
            code, out, _, _ = run_main(redmine, ["whoami"])
            self.assertEqual(out["error"], "network")

        for argv in (
            ["get", "/issues.json", "--param", "key=secret"],
            ["get", "https://evil.example/x.json"],
            ["get", "/issues.json?assigned_to_id=me"],
        ):
            code, out, _, _ = run_main(redmine, argv)
            self.assertEqual((code, out["error"]), (1, "usage"), argv)
        self.assertEqual(self.server.calls, [])


class PaginationTest(RedmineCase):
    def setUp(self):
        super().setUp()
        self.items = [{"id": n} for n in range(250)]

        def handler(params, call):
            offset = int(params.get("offset", ["0"])[0])
            limit = int(params.get("limit", ["25"])[0])
            return {
                "issues": self.items[offset : offset + limit],
                "total_count": len(self.items),
                "limit": limit,
                "offset": offset,
            }

        self.server.route("GET", "/issues.json", handler)

    def test_collect_all_follows_offset_pagination(self):
        items, complete, meta = redmine.collect_all("/issues.json")
        self.assertEqual((len(items), complete, meta["http_status"]), (250, True, 200))
        self.assertEqual([call["params"]["offset"] for call in self.calls("GET", "/issues.json")], [["0"], ["100"], ["200"]])

    def test_cap_reports_incomplete(self):
        items, complete, _ = redmine.collect_all("/issues.json", max_items=150)
        self.assertEqual((len(items), complete), (150, False))

    def test_short_page_with_total_ahead_is_not_complete(self):
        def squeezed(params, call):
            return {"issues": self.items[:10], "total_count": 250, "limit": 100, "offset": 0}

        self.server.route("GET", "/issues.json", squeezed)
        items, complete, _ = redmine.collect_all("/issues.json", max_items=30)
        self.assertEqual((len(items), complete), (30, False))

    def test_cli_get_all_and_issue(self):
        code, out, _, _ = run_main(redmine, ["get", "/issues.json", "--param", "status_id=open", "--all"])
        self.assertEqual((code, out["count"], out["complete"]), (0, 250, True))
        self.assertEqual(self.calls("GET", "/issues.json")[0]["params"]["status_id"], ["open"])

        code, out, _, _ = run_main(redmine, ["issue", ISSUE_ID])
        self.assertEqual((code, out["issue"]["id"]), (0, int(ISSUE_ID)))
        issue_call = self.calls("GET", f"/issues/{ISSUE_ID}.json")[0]
        self.assertIn("journals", ",".join(issue_call["params"]["include"]))

    def test_cli_accepts_both_unicode_and_encoded_wiki_paths(self):
        path = "/projects/bu1-sdk/wiki/Redmine使用规则.json"
        encoded = urllib.parse.quote(path)
        self.server.route("GET", encoded, {"wiki_page": {"version": 1}})
        for target in (path, encoded):
            code, out, _, _ = run_main(redmine, ["get", target])
            self.assertEqual((code, out["data"]["wiki_page"]["version"]), (0, 1))


class ConclusionPlanTest(RedmineCase):
    def test_plan_registers_action_without_any_write(self):
        code, out = self.plan()
        self.assertEqual(code, 0)
        self.assertTrue(self.action_path(out["action_id"]).exists())
        self.assertEqual(self.server.put_bodies, [])
        self.assertIn("confirm_gate", out["next"])
        self.assertIn("拟定结论", out["summary"])
        action = json.loads(self.action_path(out["action_id"]).read_text(encoding="utf-8"))
        payload = action["payload"]
        self.assertEqual(
            (payload["field_id"], payload["current_value"], payload["conclusion"], payload["redmine_url"]),
            (9, "旧结论", CONCLUSION, BASE),
        )
        self.assertRegex(payload["rules_sha256"], r"^[0-9a-f]{64}$")

    def test_plan_fails_closed_on_bad_scene(self):
        cases = {
            "no_field": {"custom_fields": [{"id": 5, "name": "问题性质", "value": ""}]},
            "dup_field": {"custom_fields": [{"id": 9, "name": "结论", "value": "a"}, {"id": 10, "name": "结论", "value": "b"}]},
            "wrong_id_returned": {"id": int(OTHER_ID)},
        }
        for name, overrides in cases.items():
            self.server.issues[ISSUE_ID].update(overrides)
            code, out = self.plan()
            self.assertEqual(code, 1, name)
            self.assertIn(out["error"], ("no_conclusion_field", "bad_response"), name)
            self.assertEqual(self.server.put_bodies, [], name)
            self.assertEqual(self.action_ids(), [], name)

        code, out = self.plan(conclusion="  ")
        self.assertEqual((code, out["error"]), (1, "bad_conclusion"))

    def test_rules_snapshot_must_be_readable(self):
        with mock.patch.object(redmine, "CONCLUSION_RULES", self.tmp / "missing.md"):
            code, out = self.plan()
            self.assertEqual((code, out["error"]), (1, "no_rules"))


class ConclusionApplyTest(RedmineCase):
    def test_apply_without_ticket_writes_nothing(self):
        _, planned = self.plan()
        code, out = self.apply(planned["action_id"])
        self.assertEqual((code, out["ok"], out["error"], out["wrote"]), (1, False, "no_ticket", False))
        self.assertIn("不要改用其他命令", out["hint"])
        self.assertEqual(self.server.put_bodies, [])
        self.assertTrue(self.action_path(planned["action_id"]).exists())

    def test_verified_writeback_uses_one_put_with_field_and_note(self):
        _, planned = self.plan()
        self.approve(planned["action_id"])
        code, out = self.apply(planned["action_id"])
        self.assertEqual((code, out["ok"], out["verified"], out["http_status"]), (0, True, True, 204))
        self.assertEqual(out["issue"]["conclusion"], CONCLUSION)

        self.assertEqual(len(self.server.put_bodies), 1)
        put = self.server.put_bodies[0]["issue"]
        self.assertEqual(put["custom_fields"], [{"id": 9, "value": CONCLUSION}])
        self.assertTrue(put["notes"].startswith("由 luyong-AI 操作："))
        self.assertIn(CONCLUSION, put["notes"])
        self.assertEqual(self.calls("PUT")[0]["headers"].get("Content-type"), "application/json")
        self.assertEqual(self.server.issues[ISSUE_ID]["custom_fields"][0]["value"], CONCLUSION)
        self.assertFalse(self.action_path(planned["action_id"]).exists())
        self.assertFalse(self.ticket_path(planned["action_id"]).exists())

        again_code, again = self.apply(planned["action_id"])
        self.assertEqual((again_code, again["error"]), (1, "unknown_action"))
        self.assertEqual(len(self.server.put_bodies), 1)

    def test_issue_state_drift_refuses_without_write(self):
        _, planned = self.plan()
        self.approve(planned["action_id"])
        self.server.issues[ISSUE_ID]["custom_fields"][0]["value"] = "别人改过的结论"
        code, out = self.apply(planned["action_id"])
        self.assertEqual((code, out["ok"], out["error"], out["wrote"]), (1, False, "changed", False))
        self.assertIn("current_value", out["message"])
        self.assertEqual(self.server.put_bodies, [])
        self.assertFalse(self.action_path(planned["action_id"]).exists())
        self.assertFalse(self.ticket_path(planned["action_id"]).exists())

    def test_field_id_or_field_presence_drift_refuses_without_write(self):
        _, planned = self.plan()
        self.approve(planned["action_id"])
        self.server.issues[ISSUE_ID]["custom_fields"][0]["id"] = 11
        code, out = self.apply(planned["action_id"])
        self.assertEqual((code, out["error"], out["wrote"]), (1, "changed", False))
        self.assertEqual(self.server.put_bodies, [])

        _, second = self.plan(conclusion="第二次")
        self.approve(second["action_id"])
        self.server.issues[ISSUE_ID]["custom_fields"] = []
        code, out = self.apply(second["action_id"])
        self.assertEqual((code, out["error"], out["wrote"]), (1, "state_changed", False))
        self.assertEqual(self.server.put_bodies, [])
        self.assertFalse(self.action_path(second["action_id"]).exists())

    def test_rules_snapshot_drift_refuses_without_write(self):
        rules = self.write(self.tmp / "rules.md", "规则 v1\n")
        with mock.patch.object(redmine, "CONCLUSION_RULES", rules):
            _, planned = self.plan()
            self.approve(planned["action_id"])
            rules.write_text("规则 v2：结论要求变了\n", encoding="utf-8")
            code, out = self.apply(planned["action_id"])
        self.assertEqual((code, out["error"], out["wrote"]), (1, "changed", False))
        self.assertEqual(self.server.put_bodies, [])

    def test_instance_url_drift_discards_action(self):
        _, planned = self.plan()
        self.approve(planned["action_id"])
        self.patch_env({"REDMINE_URL": "https://other-redmine.example.invalid"})
        code, out = self.apply(planned["action_id"])
        self.assertEqual((code, out["error"]), (1, "changed"))
        self.assertEqual(self.server.put_bodies, [])
        self.assertFalse(self.action_path(planned["action_id"]).exists())

    def test_readback_mismatch_reports_write_and_keeps_action(self):
        _, planned = self.plan()
        self.approve(planned["action_id"])
        self.server.serve_put_issue(inert=True)
        code, out = self.apply(planned["action_id"])
        self.assertEqual((code, out["ok"], out["error"], out["wrote"], out["verified"]), (1, False, "verify_failed", True, False))
        self.assertIn("不要声称完成", out["message"])
        self.assertTrue(self.action_path(planned["action_id"]).exists())
        retry_code, retry = self.apply(planned["action_id"])
        self.assertEqual((retry_code, retry["error"]), (1, "no_ticket"))
        self.assertEqual(len(self.server.put_bodies), 1)

    def test_put_http_failure_never_claims_success(self):
        _, planned = self.plan()
        self.approve(planned["action_id"])
        self.server.routes.pop("PUT /issues/%s.json" % ISSUE_ID)

        def failing_put(request, timeout):
            if request.get_method() == "PUT":
                raise urllib.error.HTTPError(request.full_url, 422, "Unprocessable", {}, io.BytesIO(b'{"errors":["x"]}'))
            return self.server(request, timeout)

        with mock.patch.object(redmine, "_urlopen", failing_put):
            code, out = self.apply(planned["action_id"])
        self.assertEqual((code, out["ok"], out["error"], out["wrote"]), (1, False, "write_failed", None))
        self.assertIn("不要声称已写入", out["message"])
        self.assertFalse(self.ticket_path(planned["action_id"]).exists())

    def test_expired_ticket_is_refused_without_write(self):
        _, planned = self.plan()
        self.approve(planned["action_id"], issued_at=time.time() - self.gate.TICKET_TTL_SECONDS - 1)
        code, out = self.apply(planned["action_id"])
        self.assertEqual((code, out["error"], out["wrote"]), (1, "expired_ticket", False))
        self.assertEqual(self.server.put_bodies, [])


if __name__ == "__main__":
    unittest.main()
