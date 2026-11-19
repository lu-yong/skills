"""commit-gerrit/scripts/commit_gerrit.py：三个门禁写入口的端到端行为。"""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from support import GateStateCase, load_script, run_main

module = load_script("commit-gerrit", "commit_gerrit.py")

HOOK = """#!/bin/sh
if ! grep -q '^Change-Id: I[0-9a-f]\\{40\\}$' "$1"; then
  printf '\\nChange-Id: I%s\\n' "$(git hash-object "$1")" >> "$1"
fi
"""

# 本地传输下 git 以 "gerrit receive-pack <dir>" 调用包装器。
GERRIT_WRAPPER = """#!/bin/sh
[ "$1" = "receive-pack" ] && shift
exec git receive-pack "$@"
"""

# 假 SSH：把 git 对 ssh:// 远端的调用原样交给本地 shell 执行。
# host 用登记表里的 git.nationalchip.com，路径是临时目录里的裸仓库。
FAKE_SSH = """#!/bin/sh
for last; do :; done
exec sh -c "$last"
"""


class CommitGerritBase(GateStateCase):
    def setUp(self) -> None:
        super().setUp()
        self.write(self.tmp / "bin" / "gerrit", GERRIT_WRAPPER).chmod(0o755)
        self.write(self.tmp / "bin" / "ssh", FAKE_SSH).chmod(0o755)
        patcher = mock.patch.dict(
            os.environ,
            {"PATH": str(self.tmp / "bin") + os.pathsep + os.environ["PATH"], "GIT_SSH_COMMAND": str(self.tmp / "bin" / "ssh")},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.issue = {
            "id": "42",
            "subject": "示例任务标题",
            "project": "bu1-sdk",
            "tracker": "任务",
            "status": "进行中",
        }
        patcher = mock.patch.object(module, "read_issue", side_effect=self._read_issue)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _read_issue(self, issue):
        """默认读取行为：问题号先过正整数校验，再返回固定详情。"""
        if not module.redmine.ISSUE_ID_RE.match(str(issue or "")):
            raise module.redmine.RedmineError("bad_issue_id", f"问题编号必须是正整数，得到：{issue!r}。")
        return dict(self.issue, id=str(issue))

    def workspace(self):
        """假 SSH 裸仓库目标 + topic 工作分支 + 会生成 Change-Id 的 hook。"""
        dest = self.tmp / "dest.git"
        self.git(self.tmp, "init", "-q", "--bare", str(dest))
        work = self.tmp / "work"
        work.mkdir()
        self.git(work, "init", "-q")
        self.write(work / ".git" / "hooks" / "commit-msg", HOOK).chmod(0o755)
        url = f"ssh://git.nationalchip.com{dest}"
        self.git(work, "remote", "add", "origin", url)
        self.write(work / "base.txt", "base\n")
        self.git(work, "add", "base.txt")
        self.git(work, "commit", "-qm", "base commit")
        self.git(work, "push", "-q", "origin", "HEAD:refs/heads/main")
        self.git(work, "config", "branch.topic.remote", "origin")
        self.git(work, "config", "branch.topic.merge", "refs/heads/main")
        self.git(work, "checkout", "-q", "-b", "topic")
        return work, dest

    def call(self, work, *argv):
        return run_main(module, list(argv), cwd=work)

    def message_file(self, text=None) -> str:
        self._message = text if text is not None else getattr(self, "_message", "fix: [42]: 修复示例问题\n")
        return str(self.write(self.tmp / "message.txt", self._message))

    def plan_stage(self, work, *extra, mode="new"):
        return self.call(
            work, "stage", "--plan", "--issue", "42", "--mode", mode, "--message-file", self.message_file(), *extra
        )

    def stage(self, work, *extra, mode="new"):
        code, out, _, _ = self.plan_stage(work, *extra, mode=mode)
        assert code == 0, out
        self.approve(out["action_id"])
        result = self.call(work, "stage", "--action", out["action_id"])
        return (result[0], result[1]), out

    def commit(self, work, stage_out, mode="new"):
        code, plan, _, _ = self.call(work, "commit-plan", "--mode", mode, "--stage-action", stage_out["action_id"])
        assert code == 0, plan
        self.approve(plan["action_id"])
        result = self.call(work, "commit", "--action", plan["action_id"])
        return (result[0], result[1]), plan

    def push(self, work, sha, commit_action_id):
        code, plan, _, _ = self.call(work, "push-plan", "--commit-action", commit_action_id, "--sha", sha)
        assert code == 0, plan
        self.approve(plan["action_id"])
        result = self.call(work, "push", "--action", plan["action_id"])
        return (result[0], result[1]), plan


class CommitGerritCase(CommitGerritBase):
    # ---------------------------------------------------------------- 全流程

    def test_full_flow_stages_commits_and_pushes_exact_sha(self):
        work, dest = self.workspace()
        self.message_file("feat: [42]: 修复示例问题\n\n正文说明本次修改内容。\n")
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["staged_paths"], ["a.txt"])
        self.assertEqual(out["mode"], "new")
        self.assertEqual(out["destination"]["dest_branch"], "main")
        self.assertEqual(out["destination"]["host"], "git.nationalchip.com")
        self.assertNotIn("user:secret@", json.dumps(out))  # 凭据安全：输出不泄露内嵌凭据

        (code, commit), commit_plan = self.commit(work, plan)
        self.assertEqual(code, 0, commit)
        sha = commit["sha"]
        self.assertFalse(commit["amend"])
        self.assertTrue(commit["change_id"].startswith("I"))

        (code, pushed), _ = self.push(work, sha, commit_plan["action_id"])
        self.assertEqual(code, 0, pushed)
        self.assertEqual(self.git(dest, "rev-parse", "refs/for/main"), sha)

    def test_stage_without_ticket_changes_nothing(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        code, out, _, _ = self.plan_stage(work)
        self.assertEqual(code, 0, out)
        code, refused, _, _ = self.call(work, "stage", "--action", out["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "no_ticket")
        self.assertEqual(self.git(work, "diff", "--cached", "--name-only"), "")

    def test_state_drift_after_stage_plan_voids_action(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        code, out, _, _ = self.plan_stage(work)
        self.assertEqual(code, 0, out)
        self.approve(out["action_id"])
        self.write(work / "a.txt", "又改了\n")
        code, refused, _, _ = self.call(work, "stage", "--action", out["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "changed")
        self.assertEqual(self.git(work, "diff", "--cached", "--name-only"), "")
        self.assertFalse((self.state_dir / "actions" / f"{out['action_id']}.json").exists())
        self.assertFalse((self.state_dir / "tickets" / f"{out['action_id']}.json").exists())

    # ---------------------------------------------------------------- 部分暂存与范围

    def test_stage_preserves_partial_staging_versions(self):
        """范围内已有暂存版本的路径原样保留，只暂存其余范围内容。"""
        work, _ = self.workspace()
        self.write(work / "a.txt", "第一版\n")
        self.git(work, "add", "a.txt")
        self.write(work / "b.txt", "范围内新增\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["staged_paths"], ["a.txt", "b.txt"])
        # a.txt 保留旧暂存版本（第一版），不是工作区的覆盖版。
        staged_content = self.git(work, "cat-file", "-p", ":a.txt")
        self.assertEqual(staged_content, "第一版")
        (code, commit), _ = self.commit(work, plan)
        self.assertEqual(code, 0, commit)
        committed = sorted(self.git(work, "show", "--name-only", "--format=", "HEAD").split())
        self.assertEqual(committed, ["a.txt", "b.txt"])
        import subprocess as sp

        head_content = sp.run(["git", "show", "HEAD:a.txt"], cwd=work, capture_output=True).stdout.decode()
        self.assertEqual(head_content, "第一版\n")

    def test_user_scope_with_out_of_scope_staged_path_refuses(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "确认范围\n")
        self.write(work / "b.txt", "早已暂存\n")
        self.git(work, "add", "b.txt")
        code, refused, _, _ = self.plan_stage(work, "--scope", "a.txt")
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "staged_out_of_scope")
        self.assertEqual(self.git(work, "diff", "--cached", "--name-only"), "b.txt")

    def test_user_scope_stages_only_confirmed_paths(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "范围内\n")
        self.write(work / "b.txt", "范围外\n")
        (code, out), plan = self.stage(work, "--scope", "a.txt")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["staged_paths"], ["a.txt"])

    def test_default_scope_snapshot_records_full_index(self):
        """默认范围下快照的暂存哈希覆盖完整索引；范围外已有暂存也随提交走。"""
        work, _ = self.workspace()
        self.write(work / "b.txt", "早已暂存\n")
        self.git(work, "add", "b.txt")
        code, out, _, _ = self.plan_stage(work)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["snapshot"]["staged_paths"], ["b.txt"])
        import subprocess

        raw = subprocess.run(["git", "ls-files", "--stage", "-z"], cwd=work, capture_output=True).stdout
        import hashlib

        self.assertEqual(out["snapshot"]["staged_hash"], hashlib.sha256(raw).hexdigest())

    # ---------------------------------------------------------------- 回执链

    def test_commit_plan_requires_stage_receipt(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        code, out, _, _ = self.plan_stage(work)
        assert code == 0
        # 只登记未执行：没有回执。
        code, refused, _, _ = self.call(work, "commit-plan", "--mode", "new", "--stage-action", out["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "no_receipt")

    def test_commit_plan_refuses_when_index_changed_after_stage(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        self.write(work / "c.txt", "stage 之后又暂存\n")
        self.git(work, "add", "c.txt")
        code, refused, _, _ = self.call(work, "commit-plan", "--mode", "new", "--stage-action", plan["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "index_changed_since_stage")

    def test_commit_plan_refuses_wrong_mode(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        code, refused, _, _ = self.call(work, "commit-plan", "--mode", "amend", "--stage-action", plan["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "mode_mismatch")

    def test_push_plan_requires_commit_receipt_and_matching_sha(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        (code, commit), commit_plan = self.commit(work, plan)
        self.assertEqual(code, 0, commit)
        code, refused, _, _ = self.call(work, "push-plan", "--commit-action", commit_plan["action_id"], "--sha", "0" * 40)
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "sha_mismatch")
        code, refused, _, _ = self.call(work, "push-plan", "--commit-action", "deadbeefdead", "--sha", commit["sha"])
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "no_receipt")

    # ---------------------------------------------------------------- amend

    def test_amend_preserves_subject_and_change_id_and_inserts_before_footer(self):
        work, dest = self.workspace()
        base_sha = self.git(work, "rev-parse", "HEAD")
        base_message = self.git(work, "log", "-1", "--format=%B")
        base_change_id = module.gerrit.change_id_of(base_message)
        self.message_file("追加：补充说明本次修复范围。\n")
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work, mode="amend")
        self.assertEqual(code, 0, out)
        (code, commit), commit_plan = self.commit(work, plan, mode="amend")
        self.assertEqual(code, 0, commit)
        self.assertTrue(commit["amend"])
        final = commit["message"]
        self.assertEqual(final.splitlines()[0], base_message.splitlines()[0])
        self.assertEqual(module.gerrit.change_id_of(final), base_change_id)
        self.assertLess(final.index("追加：补充说明"), final.index("Change-Id:"))
        self.assertNotEqual(commit["sha"], base_sha)

        (code, pushed), _ = self.push(work, commit["sha"], commit_plan["action_id"])
        self.assertEqual(code, 0, pushed)
        self.assertEqual(self.git(dest, "rev-parse", "refs/for/main"), commit["sha"])

    def test_amend_commits_exactly_resulting_tree(self):
        """amend 验证用「新树 vs 旧 HEAD 树」：改写后实际改动 = 本次暂存内容。"""
        work, _ = self.workspace()
        self.message_file("追加：amend 说明。\n")
        self.write(work / "b.txt", "amend 内容\n")
        (code, out), plan = self.stage(work, mode="amend")
        self.assertEqual(code, 0, out)
        (code, commit), _ = self.commit(work, plan, mode="amend")
        self.assertEqual(code, 0, commit)
        changed = sorted(
            line for line in self.git(work, "diff", "--name-only", commit["old_head"], commit["sha"]).splitlines() if line
        )
        self.assertEqual(changed, ["b.txt"])
        self.assertIn("base.txt", self.git(work, "ls-tree", "--name-only", commit["sha"]).split())

    # ---------------------------------------------------------------- commit 漂移

    def test_unstaged_drift_does_not_invalidate_commit(self):
        """提交动作只绑定索引、HEAD、分支与 hook；范围外未暂存修改不影响提交。"""
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        code, commit_plan, _, _ = self.call(work, "commit-plan", "--mode", "new", "--stage-action", plan["action_id"])
        self.assertEqual(code, 0, commit_plan)
        self.approve(commit_plan["action_id"])
        self.write(work / "b.txt", "范围外\n")
        code, commit, _, _ = self.call(work, "commit", "--action", commit_plan["action_id"])
        self.assertEqual(code, 0, commit)
        committed = self.git(work, "show", "--name-only", "--format=", "HEAD").split()
        self.assertEqual(committed, ["a.txt"])

    def test_index_drift_after_commit_plan_refuses(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        code, commit_plan, _, _ = self.call(work, "commit-plan", "--mode", "new", "--stage-action", plan["action_id"])
        self.assertEqual(code, 0, commit_plan)
        self.approve(commit_plan["action_id"])
        self.write(work / "b.txt", "后来暂存\n")
        self.git(work, "add", "b.txt")
        head_before = self.git(work, "rev-parse", "HEAD")
        code, refused, _, _ = self.call(work, "commit", "--action", commit_plan["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "changed")
        self.assertEqual(self.git(work, "rev-parse", "HEAD"), head_before)
        self.assertEqual(self.git(work, "diff", "--cached", "--name-only").split(), ["a.txt", "b.txt"])

    def test_commit_refuses_when_hook_adds_more_than_change_id(self):
        """hook 除 Change-Id 外改写消息（比如加了别的尾注）时不得推送。"""
        work, _ = self.workspace()
        greedy = HOOK + 'printf "Extra: 由 hook 偷加\\n" >> "$1"\n'
        self.write(work / ".git" / "hooks" / "commit-msg", greedy).chmod(0o755)
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        code, commit_plan, _, _ = self.call(work, "commit-plan", "--mode", "new", "--stage-action", plan["action_id"])
        self.assertEqual(code, 0, commit_plan)
        self.approve(commit_plan["action_id"])
        code, refused, _, _ = self.call(work, "commit", "--action", commit_plan["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "message_rewritten")

    def test_commit_refuses_when_hook_result_has_no_change_id(self):
        work, _ = self.workspace()
        self.write(work / ".git" / "hooks" / "commit-msg", "#!/bin/sh\nexit 0\n").chmod(0o755)
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        code, commit_plan, _, _ = self.call(work, "commit-plan", "--mode", "new", "--stage-action", plan["action_id"])
        self.assertEqual(code, 0, commit_plan)
        self.approve(commit_plan["action_id"])
        code, refused, _, _ = self.call(work, "commit", "--action", commit_plan["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "missing_change_id")
        self.assertIn("不要推送", refused["message"])

    def test_commit_resulting_tree_must_match_index_tree(self):
        """提交结果树必须等于确认时的索引树：hook 或配置造成的差异直接拒绝。"""
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        code, commit_plan, _, _ = self.call(work, "commit-plan", "--mode", "new", "--stage-action", plan["action_id"])
        self.assertEqual(code, 0, commit_plan)
        self.approve(commit_plan["action_id"])
        # 提交后、验证前把结果树换掉：模拟树漂移，必须拒绝且不推送。
        real_rev_parse_tree = module._git_text

        def fake(*args, **kwargs):
            if args[:2] == ("rev-parse", None) or (args and args[0] == "rev-parse" and args[-1].endswith("^{tree}")):
                return "4b825dc642cb6eb9a060e54bf8d69288fbee4904\n"
            return real_rev_parse_tree(*args, **kwargs)

        with mock.patch.object(module, "_git_text", side_effect=fake):
            code, refused, _, _ = self.call(work, "commit", "--action", commit_plan["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "tree_mismatch")

    # ---------------------------------------------------------------- push

    def test_push_refuses_when_head_moved_after_plan(self):
        work, dest = self.workspace()
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        (code, commit), commit_plan = self.commit(work, plan)
        self.assertEqual(code, 0, commit)
        code, push_plan, _, _ = self.call(work, "push-plan", "--commit-action", commit_plan["action_id"], "--sha", commit["sha"])
        self.assertEqual(code, 0, push_plan)
        self.approve(push_plan["action_id"])
        self.write(work / "c.txt", "额外提交\n")
        self.git(work, "add", "c.txt")
        self.git(work, "commit", "-qm", "later commit")
        code, refused, _, _ = self.call(work, "push", "--action", push_plan["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "changed")
        self.assertEqual(self.git(dest, "rev-parse", "--verify", "refs/for/main", check=False), "")

    def test_push_refuses_non_tip_sha(self):
        work, _ = self.workspace()
        base_sha = self.git(work, "rev-parse", "HEAD")
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        (code, commit), commit_plan = self.commit(work, plan)
        self.assertEqual(code, 0, commit)
        code, refused, _, _ = self.call(
            work, "push-plan", "--commit-action", commit_plan["action_id"], "--sha", base_sha
        )
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "sha_mismatch")

    def test_push_refuses_when_destination_drifts_after_plan(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        (code, commit), commit_plan = self.commit(work, plan)
        self.assertEqual(code, 0, commit)
        code, push_plan, _, _ = self.call(work, "push-plan", "--commit-action", commit_plan["action_id"], "--sha", commit["sha"])
        self.assertEqual(code, 0, push_plan)
        self.approve(push_plan["action_id"])
        self.git(work, "config", "branch.topic.merge", "refs/heads/other")
        code, refused, _, _ = self.call(work, "push", "--action", push_plan["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "changed")

    # ---------------------------------------------------------------- 消息与 hook 路径

    def test_message_lint_rejects_bad_subject(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        self.message_file("fix: [42]: " + "标" * 51 + "\n")
        code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "message_lint")
        self.message_file("feature: [42]: 不合法类型\n")
        code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "message_lint")
        self.message_file("fix: [43]: 问题号对不上\n")
        code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "message_lint")
        self.assertIn("问题号", refused["message"])
        self.message_file("fix: [42]: Fix the thing by hand\n")
        code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertIn("中文动词", refused["message"])
        self.message_file("fix: [42]: 修复问题。\n")
        code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertIn("句号", refused["message"])
        self.message_file("fix: [42]: 修复问题\n正文紧跟标题没有空行。\n")
        code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertIn("空一行", refused["message"])
        self.message_file("fix: [42]: 修复问题\n\nChange-Id: I" + "1" * 40 + "\n")
        code, refused, _, _ = self.plan_stage(work)
        self.assertEqual((code, refused["error"]), (1, "message_lint"))
        self.assertIn("commit-msg hook", refused["message"])

    def test_both_bracket_styles_pass_lint(self):
        for subject in ("fix: [42]: 带括号问题号", "fix: 42: 不带括号问题号"):
            self.assertEqual(module.lint_message(subject + "\n\n正文。\n", "42"), [], subject)

    def test_amend_retains_original_body_formatting(self):
        body = "fix: [42]: 修复问题\n\n第一段  \n\n\n第二段"
        footer = "\n\nChange-Id: I" + "1" * 40 + "\n"
        message = module.synthesize_amend(body + footer, "补充说明\n")
        self.assertEqual(message, body + "\n\n补充说明" + footer)

    def test_relative_hooks_path_is_resolved_against_repo_root(self):
        work, _ = self.workspace()
        self.git(work, "config", "core.hooksPath", "myhooks")
        self.write(work / "myhooks" / "commit-msg", HOOK).chmod(0o755)
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        (code, commit), _ = self.commit(work, plan)
        self.assertEqual(code, 0, commit)
        self.assertTrue(commit["change_id"].startswith("I"))

    def test_snapshot_binds_root_and_rules_digest(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        code, out, _, _ = self.plan_stage(work)
        self.assertEqual(code, 0, out)
        import hashlib

        rules = (module.RULES_FILE).read_bytes()
        self.assertEqual(out["snapshot"]["rules_sha256"], hashlib.sha256(rules).hexdigest())
        self.assertEqual(out["snapshot"]["root"], str(work.resolve()))

    # ---------------------------------------------------------------- 阶段零拒绝

    def test_hook_missing_refuses_before_any_write(self):
        work, _ = self.workspace()
        (work / ".git" / "hooks" / "commit-msg").chmod(0o644)
        self.write(work / "a.txt", "修改\n")
        code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "hook_missing")

    def test_host_outside_registry_is_refused(self):
        work, _ = self.workspace()
        self.git(work, "remote", "set-url", "origin", "ssh://example.invalid/tmp/dest.git")
        self.write(work / "a.txt", "修改\n")
        code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "host_not_allowed")

    def test_local_file_destination_is_refused(self):
        work, dest = self.workspace()
        self.git(work, "remote", "set-url", "origin", str(dest))
        self.write(work / "a.txt", "修改\n")
        code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "host_not_allowed")
        self.assertNotIn("ssh://git.nationalchip.com", refused["message"])

    def test_ambiguous_merge_config_is_refused(self):
        work, _ = self.workspace()
        self.git(work, "config", "--add", "branch.topic.merge", "refs/heads/other")
        self.write(work / "a.txt", "修改\n")
        code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "ambiguous_target_branch")

    def test_ambiguous_remote_config_is_refused(self):
        work, _ = self.workspace()
        self.git(work, "config", "--add", "branch.topic.remote", "other")
        self.write(work / "a.txt", "修改\n")
        code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "ambiguous_remote")

    def test_base_branch_and_missing_target_branch_are_refused(self):
        work, _ = self.workspace()
        self.git(work, "checkout", "-q", "main")
        self.git(work, "config", "branch.main.remote", "origin")
        self.git(work, "config", "branch.main.merge", "refs/heads/main")
        self.write(work / "a.txt", "修改\n")
        code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "base_branch")

        self.git(work, "checkout", "-q", "topic")
        self.git(work, "config", "--unset", "branch.topic.merge")
        code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "no_target_branch")

    def test_missing_issue_detail_stops_before_any_write(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        with mock.patch.object(module, "read_issue", side_effect=module.redmine.RedmineError("not_found", "问题 42 不存在。")):
            code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "not_found")
        self.assertEqual(self.git(work, "diff", "--cached", "--name-only"), "")

    def test_issue_number_must_be_plain_positive_integer(self):
        work, _ = self.workspace()
        for bad in ("#42", "42,43", "0", " 42"):
            code, refused, _, _ = self.call(
                work, "stage", "--plan", "--issue", bad, "--message-file", self.message_file()
            )
            self.assertEqual(code, 1, bad)
            self.assertEqual(refused["error"], "bad_issue_id", bad)






class PreflightTest(CommitGerritBase):
    def test_preflight_passes_and_reports_destination(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        code, out, _, _ = self.call(work, "preflight")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["phase0"], "ok")
        self.assertEqual(out["destination"]["dest_branch"], "main")
        self.assertEqual(out["destination"]["host"], "git.nationalchip.com")

    def test_preflight_rejects_unreachable_target(self):
        work, _ = self.workspace()
        self.git(work, "config", "branch.topic.merge", "refs/heads/nope")
        self.write(work / "a.txt", "修改\n")
        code, refused, _, _ = self.call(work, "preflight")
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "target_branch_unreachable")


class ReceiptBindingTest(CommitGerritBase):
    def test_stage_receipt_binds_head_hook_and_rules(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        import hashlib
        import json as jsonlib

        receipt = jsonlib.loads(
            (self.state_dir / "receipts" / f"stage.{plan['action_id']}.json").read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["head"], self.git(work, "rev-parse", "HEAD"))
        self.assertEqual(receipt["rules_sha256"], hashlib.sha256(module.RULES_FILE.read_bytes()).hexdigest())
        self.assertTrue(receipt["hook_sha"])

    def test_commit_plan_refuses_when_head_moved_after_stage(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        self.write(work / "z.txt", "额外交互\n")
        self.git(work, "add", "z.txt")
        self.git(work, "commit", "-qm", "side commit")
        code, refused, _, _ = self.call(work, "commit-plan", "--mode", "new", "--stage-action", plan["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "index_changed_since_stage")

    def test_commit_plan_refuses_when_rules_changed_after_stage(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        (code, out), plan = self.stage(work)
        self.assertEqual(code, 0, out)
        changed_rules = self.tmp / "changed-rules.md"
        changed_rules.write_bytes(module.RULES_FILE.read_bytes() + b"\n# drift\n")
        with mock.patch.object(module, "RULES_FILE", changed_rules):
            code, refused, _, _ = self.call(work, "commit-plan", "--mode", "new", "--stage-action", plan["action_id"])
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "rules_changed_since_stage")

    def test_amend_rejects_change_id_rewrite(self):
        """hook 换掉 Change-Id 会改写评审身份：amend 后必须拒绝。"""
        work, _ = self.workspace()
        self.message_file("追加：说明。\n")
        self.write(work / "b.txt", "amend 内容\n")
        (code, out), plan = self.stage(work, mode="amend")
        self.assertEqual(code, 0, out)
        # 每次都生成新 Change-Id 的 hook。stage 回执已绑定旧 hook，所以先换 hook 再重走 stage。
        counter = self.tmp / "hook-counter"
        rewriting = (
            "#!/bin/sh\n"
            f"n=$(cat {counter} 2>/dev/null || echo 0)\n"
            f"n=$((n+1)); echo $n > {counter}\n"
            'printf "\\nChange-Id: I%s\\n" "$(printf "%040d" $n)" >> "$1"\n'
        )
        self.write(work / ".git" / "hooks" / "commit-msg", rewriting).chmod(0o755)
        redo_code, redo, _, _ = self.plan_stage(work, mode="amend")
        self.assertEqual(redo_code, 0, redo)
        self.approve(redo["action_id"])
        run_result = self.call(work, "stage", "--action", redo["action_id"])
        self.assertEqual(run_result[0], 0, run_result[1])
        code, commit_plan, _, _ = self.call(work, "commit-plan", "--mode", "amend", "--stage-action", redo["action_id"])
        self.assertEqual(code, 0, commit_plan)
        self.approve(commit_plan["action_id"])
        code, refused, _, _ = self.call(work, "commit", "--action", commit_plan["action_id"])
        self.assertEqual(code, 1)
        self.assertIn(refused["error"], {"change_id_rewritten", "message_rewritten"})

    def test_all_preserved_scope_skips_add_and_keeps_index(self):
        """范围全部已暂存时不执行 git add，索引原样保留。"""
        work, _ = self.workspace()
        self.write(work / "a.txt", "已暂存\n")
        self.git(work, "add", "a.txt")
        real_git = module._git
        calls: list[list[str]] = []

        def spy(*args, **kwargs):
            if args and args[0] == "add":
                calls.append(list(args))
            return real_git(*args, **kwargs)

        with mock.patch.object(module, "_git", side_effect=spy):
            (code, out), plan = self.stage(work, "--scope", "a.txt")
        self.assertEqual(code, 0, out)
        self.assertEqual(calls, [])
        self.assertEqual(out["staged_paths"], ["a.txt"])




class RulesGuardTest(CommitGerritBase):
    def test_unreadable_rules_refuse_before_any_plan(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        missing = self.tmp / "no-such-rules.md"
        with mock.patch.object(module, "RULES_FILE", missing):
            code, refused, _, _ = self.plan_stage(work)
        self.assertEqual(code, 1)
        self.assertEqual(refused["error"], "rules_unreadable")

    def test_rules_drift_after_commit_plan_refuses_before_commit(self):
        work, _ = self.workspace()
        self.write(work / "a.txt", "修改\n")
        stage_result, plan = self.stage(work)
        self.assertEqual(stage_result[0], 0)
        code, commit_plan, _, _ = self.call(work, "commit-plan", "--mode", "new", "--stage-action", plan["action_id"])
        self.assertEqual(code, 0, commit_plan)
        self.approve(commit_plan["action_id"])
        old_head = self.git(work, "rev-parse", "HEAD")
        changed_rules = self.tmp / "changed-rules.md"
        changed_rules.write_bytes(module.RULES_FILE.read_bytes() + b"\n# drift\n")
        with mock.patch.object(module, "RULES_FILE", changed_rules):
            code, refused, _, _ = self.call(work, "commit", "--action", commit_plan["action_id"])
        self.assertEqual((code, refused["error"]), (1, "rules_changed_since_plan"))
        self.assertEqual(self.git(work, "rev-parse", "HEAD"), old_head)


if __name__ == "__main__":
    unittest.main()
