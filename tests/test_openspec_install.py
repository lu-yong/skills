"""Exercise the two OpenSpec entry scripts in isolated projects."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from support import REPO_ROOT, SandboxCase

ENTRIES = {
    "aosp-repo": "install-openspec-aosp-repo/scripts/install_aosp_repo.sh",
    "tdd-spec": "install-openspec-tdd/scripts/install_tdd_spec.sh",
}


class OpenSpecInstallTest(SandboxCase):
    def setUp(self):
        super().setUp()
        self.source = self.tmp / "upstream"
        self.bin = self.tmp / "bin"
        fake_openspec = self.write(self.bin / "openspec", """#!/usr/bin/env bash
set -eu
case "$1" in
    schema) test "$2" = validate
            test -f "openspec/schemas/$3/schema.yaml"
            test "${FAIL_SCHEMA_VALIDATION:-0}" != 1
            printf 'validated %s\n' "$3" ;;
    schemas) test -d openspec/schemas && printf 'listed schemas\\n' ;;
    *) exit 2 ;;
esac
""")
        fake_openspec.chmod(0o755)
        for schema in ENTRIES:
            self.write(self.source / schema / "schema.yaml", f"name: {schema}\n")

    def install(self, entry: Path, project: Path, *options: str):
        env = {**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ["PATH"]}
        return subprocess.run(
            [str(entry), "--project-root", str(project), *options],
            cwd=self.tmp, env=env, capture_output=True, text=True, timeout=15,
        )

    def test_both_entry_points_install_and_upgrade(self):
        for schema, entry in ENTRIES.items():
            with self.subTest(schema=schema):
                project = self.tmp / f"project {schema}"
                config = self.write(project / "openspec/config.yaml", "schema: spec-driven\ncontext: |\n  use Chinese\n")
                source_options = ("--source-dir", str(self.source))

                linked_skill = self.tmp / f"linked-{schema}"
                linked_skill.symlink_to((REPO_ROOT / entry).parents[1], target_is_directory=True)
                wrapper = linked_skill / "scripts" / Path(entry).name
                result = self.install(wrapper, project, *source_options)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(config.read_text(), f"schema: {schema}\ncontext: |\n  use Chinese\n")
                self.assertIn(f"validated {schema}", result.stdout)
                self.assertIn("listed schemas", result.stdout)

                installed = project / "openspec/schemas" / schema
                self.write(installed / "obsolete.md", "old artifact\n")
                self.write(self.source / schema / "schema.yaml", f"name: {schema}\nversion: 2\n")
                result = self.install(wrapper, project, "--mode", "upgrade", *source_options)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertLess(result.stdout.index("Showing diff"), result.stdout.index("Installed schema"))
                self.assertIn("+version: 2", result.stdout)
                self.assertFalse((installed / "obsolete.md").exists())
                self.assertEqual((installed / "schema.yaml").read_text(), f"name: {schema}\nversion: 2\n")

    def test_custom_config_requires_explicit_no_switch(self):
        for schema, entry in ENTRIES.items():
            with self.subTest(schema=schema):
                project = self.tmp / schema
                indent = "  " if schema == "tdd-spec" else ""
                original = f"{indent}schema: another-schema\n{indent}context: |\n{indent}  existing context\n"
                config = self.write(project / "openspec/config.yaml", original)
                wrapper = REPO_ROOT / entry
                source_options = ("--source-dir", str(self.source))
                result = self.install(wrapper, project, *source_options)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("another-schema", result.stderr)
                self.assertFalse((project / "openspec/schemas" / schema).exists())

                result = self.install(wrapper, project, "--no-set-schema", *source_options)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(config.read_text(), original)
                self.assertTrue((project / "openspec/schemas" / schema / "schema.yaml").is_file())

    def test_default_config_forms_switch_or_create_schema(self):
        schema = "aosp-repo"
        for index, source in enumerate((None, 'schema: "spec-driven"', "schema: spec-driven # default")):
            with self.subTest(source=source):
                project = self.tmp / f"config-{index}"
                config = project / "openspec/config.yaml"
                config.parent.mkdir(parents=True)
                tail = "context: keep\n" if source is not None else ""
                if source is not None:
                    config.write_text(f"{source}\n{tail}", encoding="utf-8")
                result = self.install(REPO_ROOT / ENTRIES[schema], project, "--source-dir", str(self.source))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(config.read_text(), f"schema: {schema}\n{tail}")

    def test_failed_validation_restores_schema_and_leaves_config_untouched(self):
        schema = "tdd-spec"
        project = self.tmp / "validation-error"
        original_config = "schema: spec-driven\ncontext: keep\n"
        config = self.write(project / "openspec/config.yaml", original_config)
        original_schema = self.write(project / "openspec/schemas" / schema / "schema.yaml", "previous: true\n")
        with patch.dict(os.environ, {"FAIL_SCHEMA_VALIDATION": "1"}):
            result = self.install(
                REPO_ROOT / ENTRIES[schema], project, "--mode", "upgrade", "--source-dir", str(self.source)
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Validating schema", result.stdout)
        self.assertEqual(config.read_text(), original_config)
        self.assertEqual(original_schema.read_text(), "previous: true\n")

    def test_clones_a_local_source_when_repo_url_is_overridden(self):
        self.git(self.source, "init", "-q")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-qm", "fixture schemas")
        schema = "tdd-spec"
        project = self.tmp / "clone-project"
        config = self.write(project / "openspec/config.yaml", "context: keep\n")
        result = self.install(REPO_ROOT / ENTRIES[schema], project, "--repo-url", self.source.as_uri())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config.read_text(), f"schema: {schema}\ncontext: keep\n")
