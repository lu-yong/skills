"""gerrit/scripts/gerrit.py：实例登记、remote 解析、HTTP 处理和提交消歧。"""

from __future__ import annotations

import base64
import io
import json
import os
import unittest
from unittest import mock

from support import SandboxCase, load_script, run_main

gerrit = load_script("gerrit", "gerrit.py")

SHA = "a" * 40
OTHER_SHA = "b" * 40
CHANGE_ID = "I" + "c" * 40


def body(data, status=200, xssi=True) -> tuple[int, bytes, str]:
    text = (")]}'\n" if xssi else "") + json.dumps(data)
    return 0, text.encode() + b"\n" + str(status).encode(), ""


def change(number, project="proj/demo", branch="master", change_id=CHANGE_ID, revisions=(SHA,), status="NEW"):
    return {
        "id": f"{project}~{branch}~{change_id}",
        "_number": number,
        "change_id": change_id,
        "project": project,
        "branch": branch,
        "status": status,
        "subject": f"change {number}",
        "current_revision": revisions[-1],
        "revisions": {sha: {"_number": index + 1} for index, sha in enumerate(revisions)},
    }


class FakeCurl:
    """按查询表达式回放变更列表，并记录每次请求。"""

    def __init__(self, by_query=None, responses=None, details=None):
        self.by_query = by_query or {}
        self.details = {
            str(item["_number"]): item for items in self.by_query.values() for item in items
        } if details is None else details
        self.responses = list(responses or [])
        self.calls = []

    def __call__(self, url, params, netrc, digest, insecure):
        self.calls.append({"url": url, "params": params, "digest": digest, "insecure": insecure})
        if self.responses:
            return self.responses.pop(0)
        if url.endswith("/detail"):
            number = url.rsplit("/", 2)[-2]
            return body(self.details[number]) if number in self.details else body({}, status=404)
        query = dict(params).get("q")
        start = int(dict(params).get("start", 0))
        size = int(dict(params).get("n", 100))
        items = self.by_query.get(query, [])[start : start + size]
        return body([dict(item) for item in items])


class GerritCase(SandboxCase):
    def setUp(self):
        super().setUp()
        netrc = self.tmp / "home" / ".netrc"
        netrc.write_text("machine git.nationalchip.com login u password p\n", encoding="utf-8")
        netrc.chmod(0o600)

    def use(self, fake):
        patcher = mock.patch.object(gerrit, "_curl", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake


class InstancesTest(unittest.TestCase):
    def test_registry_covers_all_three_instances(self):
        instances = gerrit.load_instances()["instances"]
        self.assertEqual(
            {name: config["host"] for name, config in instances.items()},
            {
                "internal": "git.nationalchip.com",
                "git2": "git2.nationalchip.com",
                "external": "gerrit.nationalchip.com",
            },
        )
        self.assertEqual(instances["internal"]["auth"], "digest")
        self.assertEqual(instances["git2"]["auth"], "basic")
        self.assertEqual([n for n, c in instances.items() if c["insecure_tls_fallback"]], ["external"])

    def test_push_hosts_are_instance_hosts_plus_unmapped(self):
        self.assertEqual(
            gerrit.push_hosts(),
            {"git.nationalchip.com", "git2.nationalchip.com", "gerrit.nationalchip.com", "192.168.110.229"},
        )

    def test_instance_for_host(self):
        self.assertEqual(gerrit.instance_for_host("GIT2.nationalchip.com"), "git2")
        self.assertIsNone(gerrit.instance_for_host("192.168.110.229"))
        self.assertIsNone(gerrit.instance_for_host("github.com"))
        self.assertIsNone(gerrit.instance_for_host(None))

    def test_host_aliases_map_to_their_instance_and_allow_pushes(self):
        registry = {
            "instances": {
                "internal": {
                    "base_url": "https://git.nationalchip.com/gerrit",
                    "auth": "digest",
                    "host_aliases": ["10.0.0.9"],
                }
            }
        }
        with mock.patch("builtins.open", mock.mock_open(read_data=json.dumps(registry))):
            self.assertEqual(gerrit.instance_for_host("10.0.0.9"), "internal")
            self.assertEqual(gerrit.push_hosts(), {"git.nationalchip.com", "10.0.0.9"})


class RemoteParsingTest(unittest.TestCase):
    def test_parse_remote(self):
        cases = {
            "https://git.nationalchip.com/gerrit/a/goxceed/loader": ("https", "git.nationalchip.com", "/gerrit/a/goxceed/loader"),
            "ssh://user@Git2.Nationalchip.com:29418/proj/x.git": ("ssh", "git2.nationalchip.com", "/proj/x.git"),
            "user@gerrit.nationalchip.com:proj/x": ("ssh", "gerrit.nationalchip.com", "proj/x"),
            "git.nationalchip.com:proj/x": ("ssh", "git.nationalchip.com", "proj/x"),
            "/srv/git/x.git": ("file", None, "/srv/git/x.git"),
            "../x.git": ("file", None, "../x.git"),
            "file:///srv/git/x.git": ("file", None, "/srv/git/x.git"),
        }
        for url, (scheme, host, path) in cases.items():
            self.assertEqual(gerrit.parse_remote(url), {"scheme": scheme, "host": host, "path": path}, url)

    def test_redact_url(self):
        self.assertEqual(gerrit.redact_url("https://user:secret@host/x"), "https://***@host/x")
        self.assertEqual(gerrit.redact_url("fatal: https://u:p@host/x failed"), "fatal: https://***@host/x failed")
        self.assertEqual(gerrit.redact_url("https://host/x"), "https://host/x")

    def test_project_from_remote(self):
        instances = gerrit.load_instances()["instances"]
        cases = [
            ("https://git.nationalchip.com/gerrit/a/goxceed/loader", "internal", "goxceed/loader"),
            ("https://git.nationalchip.com/gerrit/goxceed/loader.git", "internal", "goxceed/loader"),
            ("https://git.nationalchip.com/other/goxceed/loader", "internal", None),
            ("ssh://u@git.nationalchip.com:29418/goxceed/loader", "internal", "goxceed/loader"),
            ("u@git2.nationalchip.com:proj/x.git", "git2", "proj/x"),
            ("https://gerrit.nationalchip.com/a/proj/x", "external", "proj/x"),
            ("https://gerrit.nationalchip.com/proj/x", "external", "proj/x"),
        ]
        for url, instance, expected in cases:
            self.assertEqual(gerrit.project_from_remote(gerrit.parse_remote(url), instances[instance]), expected, url)

    def test_change_id_of_reads_the_last_paragraph_only(self):
        self.assertEqual(gerrit.change_id_of(f"fix: 1: 标题\n\n正文\n\nChange-Id: {CHANGE_ID}\n"), CHANGE_ID)
        self.assertEqual(gerrit.change_id_of(f"标题\n\nSigned-off-by: x\nChange-Id: {CHANGE_ID}"), CHANGE_ID)
        self.assertIsNone(gerrit.change_id_of(f"标题\n\nChange-Id: {CHANGE_ID}\n\n后面还有正文"))
        self.assertIsNone(gerrit.change_id_of(f"标题\n\nChange-Id: {CHANGE_ID}\nChange-Id: I{'d' * 40}"))
        self.assertIsNone(gerrit.change_id_of("标题\n\nChange-Id: I123"))
        self.assertIsNone(gerrit.change_id_of(""))


class RepoContextTest(SandboxCase):
    def make_repo(self, url="ssh://dev@git2.nationalchip.com:29418/proj/demo"):
        repo = self.tmp / "work"
        self.git(self.tmp, "init", "-q", "-b", "master", str(repo))
        self.write(repo / "a.txt", "one\n")
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", f"fix: 1: 标题\n\nChange-Id: {CHANGE_ID}")
        self.git(repo, "remote", "add", "origin", url)
        self.git(repo, "checkout", "-q", "-b", "topic")
        self.git(repo, "config", "branch.topic.remote", "origin")
        self.git(repo, "config", "branch.topic.merge", "refs/heads/sdk-release")
        return repo

    def test_context_is_derived_from_branch_configuration(self):
        repo = self.make_repo()
        context = gerrit.repo_context(repo)
        self.assertEqual(context["root"], str(repo))
        self.assertEqual(context["branch"], "topic")
        self.assertEqual(context["remote"], "origin")
        self.assertEqual(context["host"], "git2.nationalchip.com")
        self.assertEqual(context["instance"], "git2")
        self.assertEqual(context["project"], "proj/demo")
        self.assertEqual(context["target_branch"], "sdk-release")
        self.assertEqual(context["commit"], self.git(repo, "rev-parse", "HEAD"))
        self.assertEqual(context["change_id"], CHANGE_ID)

    def test_multiple_configured_merge_branches_leave_the_target_open(self):
        repo = self.make_repo()
        self.git(repo, "config", "--add", "branch.topic.merge", "refs/heads/other-release")
        self.assertIsNone(gerrit.repo_context(repo)["target_branch"])

    def test_credentials_in_the_remote_url_are_not_reported(self):
        repo = self.make_repo("https://dev:hunter2@git.nationalchip.com/gerrit/a/proj/demo")
        context = gerrit.repo_context(repo)
        self.assertNotIn("hunter2", json.dumps(context))
        self.assertEqual(context["project"], "proj/demo")

    def test_unknown_host_and_multiple_push_urls_leave_the_instance_open(self):
        repo = self.make_repo("ssh://dev@192.168.110.229:29418/proj/demo")
        context = gerrit.repo_context(repo)
        self.assertEqual(context["host"], "192.168.110.229")
        self.assertIsNone(context["instance"])
        self.assertIsNone(context["project"])

        self.git(repo, "remote", "set-url", "--add", "--push", "origin", "ssh://git.nationalchip.com/a")
        self.git(repo, "remote", "set-url", "--add", "--push", "origin", "ssh://git2.nationalchip.com/b")
        self.assertIsNone(gerrit.repo_context(repo)["host"])

    def test_outside_a_repository(self):
        with self.assertRaises(gerrit.GerritError) as caught:
            gerrit.repo_context(self.tmp)
        self.assertEqual(caught.exception.code, "not_a_repository")


class RequestTest(GerritCase):
    def test_internal_uses_digest_and_strips_the_xssi_prefix(self):
        fake = self.use(FakeCurl(responses=[body({"name": "me"})]))
        data, meta = gerrit.get_json("internal", "/accounts/self")
        self.assertEqual(data, {"name": "me"})
        self.assertEqual(meta, {"instance": "internal", "tls_verified": True, "http_status": 200})
        self.assertEqual(fake.calls[0]["url"], "https://git.nationalchip.com/gerrit/a/accounts/self")
        self.assertTrue(fake.calls[0]["digest"])
        self.assertFalse(fake.calls[0]["insecure"])

    def test_basic_instances_do_not_use_digest(self):
        for instance, url in (("git2", "https://git2.nationalchip.com/gerrit/a/x"), ("external", "https://gerrit.nationalchip.com/a/x")):
            fake = self.use(FakeCurl(responses=[body({})]))
            gerrit.get_json(instance, "x")
            self.assertEqual(fake.calls[0]["url"], url)
            self.assertFalse(fake.calls[0]["digest"])

    def test_json_without_the_prefix_is_parsed_unchanged(self):
        self.use(FakeCurl(responses=[body([1, 2], xssi=False)]))
        self.assertEqual(gerrit.get_json("internal", "x")[0], [1, 2])
        self.assertEqual(gerrit.parse_json(b'")]}\'x"'), ")]}'x")

    def test_tls_failure_falls_back_only_on_the_external_instance(self):
        fake = self.use(FakeCurl(responses=[(60, b"", "certificate problem"), body({"ok": 1})]))
        data, meta = gerrit.get_json("external", "x")
        self.assertEqual(data, {"ok": 1})
        self.assertFalse(meta["tls_verified"])
        self.assertEqual([call["insecure"] for call in fake.calls], [False, True])

        for instance in ("internal", "git2"):
            fake = self.use(FakeCurl(responses=[(60, b"", "certificate problem")]))
            with self.assertRaises(gerrit.GerritError) as caught:
                gerrit.get_json(instance, "x")
            self.assertEqual(caught.exception.code, "tls")
            self.assertEqual(len(fake.calls), 1)

    def test_http_and_network_errors(self):
        for status, code in ((302, "http"), (401, "auth"), (403, "forbidden"), (404, "not_found"), (500, "http")):
            self.use(FakeCurl(responses=[(0, b"Not found\n" + str(status).encode(), "")]))
            with self.assertRaises(gerrit.GerritError) as caught:
                gerrit.get_json("internal", "x")
            self.assertEqual(caught.exception.code, code)
        self.use(FakeCurl(responses=[(6, b"", "could not resolve host")]))
        with self.assertRaises(gerrit.GerritError) as caught:
            gerrit.get_json("internal", "x")
        self.assertEqual(caught.exception.code, "network")

    def test_missing_netrc_and_unknown_instance(self):
        os.remove(self.tmp / "home" / ".netrc")
        with self.assertRaises(gerrit.GerritError) as caught:
            gerrit.get_json("internal", "x")
        self.assertEqual(caught.exception.code, "no_credentials")
        with self.assertRaises(gerrit.GerritError) as caught:
            gerrit.get_json("nowhere", "x")
        self.assertEqual(caught.exception.code, "unknown_instance")

    def test_change_identifiers_are_url_encoded(self):
        self.assertEqual(gerrit.change_path("proj/x~master~I1", "/detail"), "changes/proj%2Fx~master~I1/detail")

    def test_patch_is_base64_decoded_and_raw_bytes_pass_through(self):
        patch = b"From abc\nSubject: r\xe9paration\n\ndiff --git a/x b/x\n"
        encoded = base64.b64encode(patch)
        wrapped = b"\n".join(encoded[i : i + 20] for i in range(0, len(encoded), 20))
        for payload in (encoded, wrapped, patch):
            self.use(FakeCurl(responses=[(0, payload + b"\n200", "")]))
            with io.TextIOWrapper(io.BytesIO(), encoding="utf-8") as stdout:
                with mock.patch.object(gerrit.sys, "stdout", stdout):
                    self.assertEqual(gerrit.main(["patch", "--instance", "internal", "12"]), 0)
                self.assertEqual(stdout.buffer.getvalue(), patch)


class QueryTest(GerritCase):
    def test_pages_are_followed_until_a_short_page(self):
        items = [change(n) for n in range(250)]
        fake = self.use(FakeCurl(by_query={"status:open": items}))
        changes, complete, _ = gerrit.query_changes("internal", "status:open", limit=None)
        self.assertEqual([c["_number"] for c in changes], list(range(250)))
        self.assertTrue(complete)
        self.assertEqual([dict(c["params"])["start"] for c in fake.calls], ["0", "100", "200"])

    def test_limit_reports_an_incomplete_list(self):
        self.use(FakeCurl(by_query={"q": [change(n) for n in range(30)]}))
        changes, complete, _ = gerrit.query_changes("internal", "q", limit=20)
        self.assertEqual(len(changes), 20)
        self.assertFalse(complete)

    def test_exactly_one_full_page_is_probed_before_calling_it_complete(self):
        fake = self.use(FakeCurl(by_query={"q": [change(n) for n in range(20)]}))
        changes, complete, _ = gerrit.query_changes("internal", "q", limit=20)
        self.assertEqual(len(changes), 20)
        self.assertTrue(complete)
        self.assertEqual(len(fake.calls), 2)

    def test_more_changes_flag_continues_past_a_server_side_cap(self):
        first = [change(n) for n in range(25)]
        first[-1]["_more_changes"] = True
        fake = self.use(FakeCurl(responses=[body(first), body([change(99)])]))
        changes, complete, _ = gerrit.query_changes("internal", "q", limit=None)
        self.assertEqual(len(changes), 26)
        self.assertTrue(complete)
        self.assertNotIn("_more_changes", changes[24])
        self.assertEqual(dict(fake.calls[1]["params"])["start"], "25")

    def test_cli_reports_completeness(self):
        self.use(FakeCurl(by_query={"q": [change(1), change(2)]}))
        code, out, _, _ = run_main(gerrit, ["query", "--instance", "internal", "q"])
        self.assertEqual(code, 0)
        self.assertEqual((out["ok"], out["count"], out["complete"]), (True, 2, True))

    def test_cli_errors_are_json_with_a_failing_exit_code(self):
        self.use(FakeCurl(responses=[(0, b"no\n404", "")]))
        code, out, _, _ = run_main(gerrit, ["change", "--instance", "internal", "12"])
        self.assertEqual(code, 1)
        self.assertEqual((out["ok"], out["error"], out["http_status"]), (False, "not_found", 404))


class ResolveCommitTest(GerritCase):
    def resolve(self, by_query, *, details=None, **kwargs):
        self.fake = self.use(FakeCurl(by_query=by_query, details=details))
        defaults = dict(instance="internal", sha=SHA, change_id=CHANGE_ID, project="proj/demo", branch="master", cwd=self.tmp)
        defaults.update(kwargs)
        return gerrit.resolve_commit(**defaults)

    def test_unique_change_with_exact_revision(self):
        result = self.resolve({f"commit:{SHA}": [change(7, revisions=(OTHER_SHA, SHA))]})
        self.assertEqual(result["status"], "unique")
        self.assertEqual(result["change"]["number"], 7)
        self.assertEqual(result["change"]["revision"], SHA)
        self.assertEqual(result["change"]["revision_basis"], "exact")
        self.assertEqual(result["change"]["selection_basis"], "unique")
        self.assertEqual(result["queries"], [f"commit:{SHA}", f"change:{CHANGE_ID}"])

    def test_reads_each_candidates_detail_before_applying_revision_filter(self):
        details = {"6": change(6, revisions=(SHA, OTHER_SHA)), "7": change(7, revisions=(OTHER_SHA,))}
        result = self.resolve(
            {f"commit:{SHA}": [{"_number": 6}, {"_number": 7}], f"change:{CHANGE_ID}": [{"_number": 6}]},
            details=details,
        )
        self.assertEqual(result["change"]["number"], 6)
        self.assertEqual(result["change"]["revision"], SHA)
        self.assertEqual(result["change"]["current_revision"], OTHER_SHA)
        reads = [call for call in self.fake.calls if call["url"].endswith("/detail")]
        self.assertEqual([call["url"].split("/")[-2] for call in reads], ["6", "7"])
        self.assertTrue(all(("o", "ALL_REVISIONS") in call["params"] for call in reads))

    def test_incomplete_detail_does_not_count_as_a_non_exact_revision(self):
        incomplete = change(6)
        del incomplete["revisions"]
        with self.assertRaises(gerrit.GerritError) as caught:
            self.resolve({f"commit:{SHA}": [{"_number": 6}]}, details={"6": incomplete})
        self.assertEqual(caught.exception.code, "bad_change_detail")

    def test_change_found_only_by_change_id_uses_the_current_revision(self):
        result = self.resolve({f"change:{CHANGE_ID}": [change(7, revisions=(OTHER_SHA,))]})
        self.assertEqual(result["status"], "unique")
        self.assertEqual(result["change"]["revision"], OTHER_SHA)
        self.assertEqual(result["change"]["revision_basis"], "current_revision")

    def test_layers_filter_change_id_project_and_branch(self):
        candidates = [
            change(1),
            change(2, change_id="I" + "d" * 40),
            change(3, project="proj/other"),
            change(4, branch="dev"),
        ]
        result = self.resolve({f"commit:{SHA}": candidates})
        self.assertEqual(result["status"], "unique")
        self.assertEqual(result["change"]["number"], 1)
        self.assertEqual([(l["layer"], l.get("after")) for l in result["layers"][:3]], [("change_id", 3), ("project", 2), ("branch", 1)])

    def test_exact_revision_is_preferred_over_other_candidates(self):
        candidates = [change(1, revisions=(OTHER_SHA,)), change(2, branch="master", revisions=(SHA,))]
        candidates[0]["id"] = "x1"
        candidates[1]["id"] = "x2"
        result = self.resolve({f"commit:{SHA}": [candidates[1]], f"change:{CHANGE_ID}": candidates})
        self.assertEqual(result["status"], "unique")
        self.assertEqual(result["change"]["number"], 2)

    def test_ambiguity_is_reported_and_resolved_by_pick(self):
        candidates = [change(1), change(2)]
        candidates[0]["id"], candidates[1]["id"] = "x1", "x2"
        result = self.resolve({f"commit:{SHA}": candidates})
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual([c["number"] for c in result["candidates"]], [1, 2])

        picked = self.resolve({f"commit:{SHA}": candidates}, pick=2)
        self.assertEqual(picked["status"], "unique")
        self.assertEqual(picked["change"]["selection_basis"], "user_selected")

        with self.assertRaises(gerrit.GerritError) as caught:
            self.resolve({f"commit:{SHA}": candidates}, pick=9)
        self.assertEqual(caught.exception.code, "bad_pick")

    def test_no_candidates(self):
        self.assertEqual(self.resolve({})["status"], "none")
        self.assertEqual(self.resolve({f"commit:{SHA}": [change(1, branch="dev")]})["status"], "none")

    def test_underivable_inputs_are_returned_as_questions(self):
        self.assertEqual(self.resolve({}, instance=None)["status"], "needs_instance")
        self.assertEqual(self.resolve({}, instance=None)["options"], ["external", "git2", "internal"])
        self.assertEqual(len(self.fake.calls), 0)

        candidates = [change(1), change(2, project="proj/other")]
        candidates[0]["id"], candidates[1]["id"] = "x1", "x2"
        result = self.resolve({f"commit:{SHA}": candidates}, project=None)
        self.assertEqual((result["status"], result["options"]), ("needs_project", ["proj/demo", "proj/other"]))

        result = self.resolve({f"commit:{SHA}": [change(1)]}, branch=None)
        self.assertEqual((result["status"], result["options"]), ("needs_branch", ["master"]))

    def test_abbreviated_sha_is_rejected(self):
        with self.assertRaises(gerrit.GerritError) as caught:
            self.resolve({}, sha="abc1234")
        self.assertEqual(caught.exception.code, "bad_sha")

    def test_inputs_come_from_the_repository_when_not_given(self):
        repo = self.tmp / "work"
        self.git(self.tmp, "init", "-q", "-b", "master", str(repo))
        self.write(repo / "a.txt", "one\n")
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", f"fix: 1: 标题\n\nChange-Id: {CHANGE_ID}")
        self.git(repo, "remote", "add", "origin", "https://git.nationalchip.com/gerrit/a/proj/demo")
        self.git(repo, "checkout", "-q", "-b", "topic")
        self.git(repo, "config", "branch.topic.remote", "origin")
        self.git(repo, "config", "branch.topic.merge", "refs/heads/master")
        head = self.git(repo, "rev-parse", "HEAD")

        self.fake = self.use(FakeCurl(by_query={f"commit:{head}": [change(5, revisions=(head,))]}))
        result = gerrit.resolve_commit(cwd=repo)
        self.assertEqual(result["status"], "unique")
        self.assertEqual(result["inputs"]["sources"], {k: "repository" for k in ("sha", "change_id", "instance", "project", "branch")})
        self.assertEqual(result["change"]["number"], 5)

        self.git(repo, "remote", "set-url", "origin", "ssh://dev@192.168.110.229:29418/proj/demo")
        self.assertEqual(gerrit.resolve_commit(cwd=repo)["status"], "needs_instance")
        result = gerrit.resolve_commit(cwd=repo, instance="git2")
        self.assertEqual(result["status"], "unique")
        self.assertEqual(result["inputs"]["project"], "proj/demo")
        self.assertEqual(result["instance"], "git2")


if __name__ == "__main__":
    unittest.main()
