from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from ralph_bench.adapters.codex_execution import (
    CodexAttemptExecutor,
    ProcessExecutionResult,
    SubprocessExecutor,
    credential_secret_values,
    parse_codex_jsonl,
    redact_evidence_file,
)
from ralph_bench.adapters.contracts import InvocationPlan
from ralph_bench.events import EventRecorder
from ralph_bench.execution import InvocationAdmission


class FakeRunner:
    def __init__(self, result: ProcessExecutionResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def run(self, argv, *, prompt, cwd, env, stdout_path, stderr_path, timeout_seconds, on_prompt_delivered):
        self.calls.append({
            "argv": tuple(argv),
            "prompt": prompt,
            "cwd": cwd,
            "env": dict(env),
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "timeout_seconds": timeout_seconds,
        })
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(
            '{"type":"thread.started","thread_id":"thread-test"}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"done"}}\n'
            '{"type":"turn.completed","usage":{"input_tokens":30,"output_tokens":9,"reasoning_output_tokens":3,"cached_input_tokens":5,"total_tokens":39}}\n',
            encoding="utf-8",
        )
        stderr_path.write_text("stderr\n", encoding="utf-8")
        on_prompt_delivered()
        return self.result


class CodexExecutionTests(unittest.TestCase):
    def test_fixture_stream_normalizes_session_message_and_usage(self) -> None:
        path = Path(__file__).parent / "fixtures" / "codex_stream.jsonl"
        summary = parse_codex_jsonl(path)
        self.assertEqual(summary.events_seen, 3)
        self.assertEqual(summary.session_id, "thread-test")
        self.assertEqual(summary.final_message, "Working")
        self.assertEqual(summary.turns, 1)
        self.assertEqual(summary.usage["input_tokens"], 30)
        self.assertEqual(summary.usage["output_tokens"], 9)
        self.assertEqual(summary.usage["reasoning_tokens"], 3)
        self.assertEqual(summary.usage["cache_read_tokens"], 5)
        self.assertEqual(summary.usage["total_tokens"], 39)

    def test_malformed_lines_are_diagnosed_without_copying_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "events.jsonl"
            path.write_text(
                "not-json secret-token\n"
                '{"type":"item.completed","item":{"type":"agent_message","text":"token=secret-token"}}\n',
                encoding="utf-8",
            )
            summary = parse_codex_jsonl(path, secret_values=("secret-token",))
            self.assertEqual(summary.events_seen, 1)
            self.assertEqual(summary.malformed_lines, 1)
            self.assertEqual(summary.final_message, "token=[REDACTED]")
            self.assertNotIn("secret-token", json.dumps(summary.to_dict()))

    def test_raw_evidence_is_atomically_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "vendor.jsonl"
            path.write_text(
                '{"type":"item.completed","text":"Bearer exact-secret-value",'
                '"access_token":"second-secret","input_tokens":42}\n',
                encoding="utf-8",
            )
            redact_evidence_file(path, ("exact-secret-value",))
            rendered = path.read_text(encoding="utf-8")
            self.assertNotIn("exact-secret-value", rendered)
            self.assertNotIn("second-secret", rendered)
            self.assertIn("[REDACTED]", rendered)
            self.assertEqual(json.loads(rendered)["input_tokens"], 42)
            self.assertFalse(path.with_name(path.name + ".redacting").exists())

    def test_credential_json_yields_only_secret_context_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "auth.json"
            path.write_text(
                json.dumps(
                    {
                        "auth_mode": "chatgpt",
                        "tokens": {
                            "access_token": "access-secret-value",
                            "refresh_token": "refresh-secret-value",
                        },
                        "profile": {"display_name": "not-a-secret-value"},
                    }
                ),
                encoding="utf-8",
            )
            values = credential_secret_values(path)
            self.assertIn("access-secret-value", values)
            self.assertIn("refresh-secret-value", values)
            self.assertNotIn("not-a-secret-value", values)

    def test_executor_admits_only_after_prompt_delivery_and_returns_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            runner = FakeRunner(ProcessExecutionResult(0, True, True))
            recorder = EventRecorder()
            admission = InvocationAdmission(1, recorder)
            executor = CodexAttemptExecutor(
                plan=InvocationPlan(("codex", "exec", "-"), working_directory=str(workspace)),
                workspace=workspace,
                evidence_root=root / "events" / "raw",
                prompt="build the artifact",
                environment={"HOME": str(root / "home")},
                timeout_seconds=12,
                runner=runner,
                secret_values=("thread-test",),
            )
            result = executor(1, None, admission)
            self.assertTrue(admission.started)
            self.assertEqual(runner.calls[0]["prompt"], "build the artifact")
            self.assertEqual(runner.calls[0]["cwd"], workspace)
            self.assertEqual(result.terminal_reason, "process_exited")
            self.assertEqual(result.candidate_path, workspace)
            self.assertEqual(len(result.raw_evidence_refs), 3)
            summary = json.loads((root / "events/raw/codex-attempt-001.summary.json").read_text())
            self.assertEqual(summary["usage"]["total_tokens"], 39)
            self.assertNotIn(
                "thread-test",
                (root / "events/raw/codex-attempt-001.jsonl").read_text(),
            )
            self.assertEqual(
                sum(event.event_type == "model_invocation.started" for event in recorder.snapshot()),
                1,
            )

    def test_executor_preserves_nonzero_and_timeout_outcomes(self) -> None:
        for process_result, expected in (
            (ProcessExecutionResult(7, True, True), "process_exited_7"),
            (ProcessExecutionResult(-15, True, True, timed_out=True, termination="timeout_process_group_terminated"), "timeout"),
        ):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workspace = root / "workspace"
                workspace.mkdir()
                runner = FakeRunner(process_result)
                admission = InvocationAdmission(1, EventRecorder())
                result = CodexAttemptExecutor(
                    plan=InvocationPlan(("codex", "exec", "-")),
                    workspace=workspace,
                    evidence_root=root / "raw",
                    prompt="prompt",
                    environment={},
                    timeout_seconds=1,
                    runner=runner,
                )(1, None, admission)
                self.assertEqual(result.terminal_reason, expected)
                self.assertTrue(admission.started)

    def test_executor_accepts_remaining_budget_callback_and_fails_when_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            runner = FakeRunner(ProcessExecutionResult(0, True, True))
            executor = CodexAttemptExecutor(
                plan=InvocationPlan(("codex", "exec", "-")),
                workspace=workspace,
                evidence_root=root / "raw",
                prompt="prompt",
                environment={},
                timeout_seconds=lambda: 0.25,
                runner=runner,
            )
            result = executor(1, None, InvocationAdmission(1, EventRecorder()))
            self.assertEqual(result.terminal_reason, "process_exited")
            self.assertEqual(runner.calls[0]["timeout_seconds"], 0.25)

            exhausted = CodexAttemptExecutor(
                plan=InvocationPlan(("codex", "exec", "-")),
                workspace=workspace,
                evidence_root=root / "raw-exhausted",
                prompt="prompt",
                environment={},
                timeout_seconds=lambda: 0,
                runner=runner,
            )
            with self.assertRaisesRegex(RuntimeError, "budget is exhausted"):
                exhausted(1, None, InvocationAdmission(1, EventRecorder()))

    def test_subprocess_timeout_terminates_dedicated_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cwd = root / "cwd"
            cwd.mkdir()
            runner = SubprocessExecutor(terminate_grace_seconds=0.05)
            result = runner.run(
                (sys.executable, "-c", "import time; time.sleep(30)"),
                prompt="prompt",
                cwd=cwd,
                env={"PATH": "/usr/bin:/bin"},
                stdout_path=root / "stdout.jsonl",
                stderr_path=root / "stderr.txt",
                timeout_seconds=0.05,
                on_prompt_delivered=lambda: None,
            )
            self.assertTrue(result.spawned)
            self.assertTrue(result.prompt_delivered)
            self.assertTrue(result.timed_out)
            self.assertEqual(result.termination, "timeout_process_group_terminated")
            self.assertIsNotNone(result.returncode)
            self.assertTrue((root / "stdout.jsonl").exists())
            self.assertTrue((root / "stderr.txt").exists())

    def test_subprocess_receives_complete_file_backed_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cwd = root / "cwd"
            cwd.mkdir()
            result = SubprocessExecutor().run(
                (
                    sys.executable,
                    "-c",
                    "import json,sys; print(json.dumps({'prompt': sys.stdin.read()}))",
                ),
                prompt="complete prompt\nwith a second line",
                cwd=cwd,
                env={"PATH": "/usr/bin:/bin"},
                stdout_path=root / "stdout.jsonl",
                stderr_path=root / "stderr.txt",
                timeout_seconds=2,
                on_prompt_delivered=lambda: None,
            )
            self.assertEqual(result.returncode, 0)
            payload = json.loads((root / "stdout.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(payload["prompt"], "complete prompt\nwith a second line")


if __name__ == "__main__":
    unittest.main()
