"""测试公用：按路径加载各技能的脚本，以及隔离的门禁状态目录。"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_script(skill: str, filename: str):
    """加载 <skill>/scripts/<filename>，模块名与脚本之间互相加载时使用的一致。"""
    path = REPO_ROOT / skill / "scripts" / filename
    name = "skill_" + skill.replace("-", "_") + "_" + path.stem
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_main(module, argv: list[str], cwd: Path | str | None = None) -> tuple[int, dict | None, str, str]:
    """在进程内运行脚本的 main()，返回 (退出码, 解析后的 JSON 输出, stdout, stderr)。"""
    stdout, stderr = io.StringIO(), io.StringIO()
    previous = os.getcwd()
    if cwd is not None:
        os.chdir(cwd)
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = module.main(argv)
            except SystemExit as exc:
                code = exc.code
    finally:
        os.chdir(previous)
    if code is None:
        code = 0
    out = stdout.getvalue()
    try:
        parsed = json.loads(out) if out.strip() else None
    except ValueError:
        parsed = None
    return int(code) if isinstance(code, int) else 1, parsed, out, stderr.getvalue()


def issue_ticket(state_dir: Path | str, action: dict, issued_at: float | None = None) -> Path:
    """模拟宿主门禁在用户确认后写入凭据。只存在于测试里：脚本侧没有签发函数。"""
    path = Path(state_dir) / "tickets" / f"{action['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "action_id": action["id"],
                "digest": action["digest"],
                "issued_at": time.time() if issued_at is None else issued_at,
                "issuer": "test",
            }
        ),
        encoding="utf-8",
    )
    return path


class SandboxCase(unittest.TestCase):
    """每个用例一个临时目录；HOME 和 git 的全局配置都指向沙箱，不读用户自己的。"""

    def setUp(self) -> None:
        super().setUp()
        self._sandbox = tempfile.TemporaryDirectory(prefix="skills-test-")
        self.addCleanup(self._sandbox.cleanup)
        self.tmp = Path(self._sandbox.name).resolve()
        home = self.tmp / "home"
        home.mkdir()
        self.state_dir = self.tmp / "gate-state"
        env = {
            "HOME": str(home),
            "CONFIRM_GATE_STATE_DIR": str(self.state_dir),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Test Author",
            "GIT_AUTHOR_EMAIL": "author@example.invalid",
            "GIT_COMMITTER_NAME": "Test Committer",
            "GIT_COMMITTER_EMAIL": "committer@example.invalid",
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("XDG_STATE_HOME", "GERRIT_NETRC_FILE", "REDMINE_SECRET_FILE", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            os.environ.pop(name, None)

    def git(self, cwd: Path | str, *args: str, check: bool = True) -> str:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
        if check and result.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def write(self, path: Path | str, text: str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class GateStateCase(SandboxCase):
    """带隔离门禁状态目录的用例。"""

    def setUp(self) -> None:
        super().setUp()
        self.gate = load_script("confirm-gate", "gate.py")

    def approve(self, action_id: str, issued_at: float | None = None) -> Path:
        """按动作编号签发测试凭据，等同用户在宿主对话框里选了确认。"""
        action = json.loads((self.state_dir / "actions" / f"{action_id}.json").read_text(encoding="utf-8"))
        return issue_ticket(self.state_dir, action, issued_at)
