from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import unittest

from ralph_bench.isolation import (
    CanaryStatus,
    IsolationError,
    IsolationLevel,
    NetworkCapability,
    StagedWorkspace,
    build_isolation_report,
    build_process_environment,
    secret_environment_keys,
)


class IsolationTests(unittest.TestCase):
    def test_stages_only_public_inputs_and_cleans_owned_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source/public"
            source.mkdir(parents=True)
            (source / "prompt.txt").write_text("public")
            private = root / "source/private"
            private.mkdir()
            (private / "judge.json").write_text("secret")
            staging = root / "staging"

            staged = StagedWorkspace.create(
                base_root=staging,
                run_id="run-001",
                public_challenge_source=source,
                forbidden_roots=(root / "source",),
            )

            self.assertEqual(
                (staged.public_challenge / "prompt.txt").read_text(), "public"
            )
            self.assertFalse((staged.run_root / "private").exists())
            self.assertTrue(staged.workspace.is_dir())
            self.assertNotEqual(staged.conductor_root.parent, staged.workspace)
            file_mode = stat.S_IMODE(
                (staged.public_challenge / "prompt.txt").stat().st_mode
            )
            self.assertEqual(file_mode & 0o222, 0)

            staged.cleanup()
            self.assertFalse(staged.run_root.exists())
            self.assertFalse(staged.conductor_root.exists())
            staged.cleanup()

    def test_rejects_staging_inside_forbidden_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source/public"
            source.mkdir(parents=True)
            with self.assertRaises(IsolationError):
                StagedWorkspace.create(
                    base_root=root / "source/staging",
                    run_id="run-001",
                    public_challenge_source=source,
                    forbidden_roots=(root / "source",),
                )

    def test_rejects_staging_that_contains_the_public_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "public"
            source.mkdir()
            with self.assertRaises(IsolationError):
                StagedWorkspace.create(
                    base_root=root,
                    run_id="run-001",
                    public_challenge_source=source,
                )

            with self.assertRaises(IsolationError):
                StagedWorkspace.create(
                    base_root=root,
                    run_id="run-002",
                    public_challenge_source=source,
                    forbidden_roots=(root / "source",),
                )

    def test_rejects_symlink_in_public_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "public"
            source.mkdir()
            target = source / "target.txt"
            target.write_text("target")
            try:
                (source / "link.txt").symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this platform")
            with self.assertRaises(IsolationError):
                StagedWorkspace.create(
                    base_root=root / "staging",
                    run_id="run-001",
                    public_challenge_source=source,
                )

    def test_environment_is_allowlisted_and_secret_values_do_not_cross(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = {
                "PATH": "/usr/bin",
                "LANG": "C.UTF-8",
                "OPENAI_API_KEY": "never-copy-this",
                "UNRELATED": "drop-this",
            }
            environment = build_process_environment(
                source, scoped_home=Path(temporary) / "home"
            )
            self.assertEqual(environment["PATH"], "/usr/bin")
            self.assertNotIn("OPENAI_API_KEY", environment)
            self.assertNotIn("UNRELATED", environment)
            self.assertNotIn("never-copy-this", repr(environment))
            self.assertEqual(secret_environment_keys(environment), ())
            with self.assertRaises(IsolationError):
                build_process_environment(
                    source,
                    scoped_home=Path(temporary) / "home",
                    overrides={"SERVICE_AUTH_TOKEN": "bad"},
                )
            with self.assertRaises(IsolationError):
                build_process_environment(
                    source,
                    scoped_home=Path(temporary) / "home",
                    overrides={"CODEX_HOME": "/credentials"},
                )

    def test_best_effort_report_remains_l0_even_with_positive_evidence(self) -> None:
        clean_environment = {"PATH": "/usr/bin", "HOME": "/scoped"}
        passed = build_isolation_report(
            environment=clean_environment,
            credential_canary=CanaryStatus.PASSED,
            agent_network=NetworkCapability.UNKNOWN,
        )
        self.assertEqual(passed.level, IsolationLevel.L0)
        self.assertEqual(passed.publication_class, "unsealed")
        self.assertFalse(passed.filesystem_enforced)

        unknown = build_isolation_report(
            environment=clean_environment,
            credential_canary=CanaryStatus.UNKNOWN,
        )
        self.assertEqual(unknown.level, IsolationLevel.L0)
        self.assertEqual(unknown.publication_class, "unsealed")

        leaked = build_isolation_report(
            environment={**clean_environment, "SERVICE_AUTH_TOKEN": "fixture"},
            credential_canary=CanaryStatus.PASSED,
        )
        self.assertEqual(leaked.level, IsolationLevel.L0)
        self.assertNotIn("fixture", repr(leaked))


if __name__ == "__main__":
    unittest.main()
