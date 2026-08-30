from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ralph_bench.adapters.contracts import HarnessExecutionContext, InvocationPlan
from ralph_bench.adapters.codex_execution import ProcessExecutionResult
from ralph_bench.adapters.pi_execution import PiAttemptExecutor, parse_pi_jsonl
from ralph_bench.events import EventRecorder
from ralph_bench.execution import InvocationAdmission


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(
        self,
        argv,
        *,
        prompt,
        cwd,
        env,
        stdout_path,
        stderr_path,
        timeout_seconds,
        on_prompt_delivered,
    ):
        self.calls.append(
            {
                "argv": tuple(argv),
                "prompt": prompt,
                "cwd": cwd,
                "env": dict(env),
                "timeout_seconds": timeout_seconds,
            }
        )
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(
            '{"type":"message_end","message":{"role":"assistant",'
            '"provider":"lmstudio","model":"candidate",'
            '"content":[{"type":"text","text":"done"},{"type":"toolCall","name":"write"}],'
            '"usage":{"input":40,"output":12,"cacheRead":3}}}\n',
            encoding="utf-8",
        )
        stderr_path.write_text("stderr\n", encoding="utf-8")
        on_prompt_delivered()
        return ProcessExecutionResult(0, True, True)


class PiExecutionTests(unittest.TestCase):
    def test_pi_jsonl_normalizes_usage_identity_and_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "events.jsonl"
            path.write_text(
                "not-json\n"
                '{"type":"message_end","sessionId":"session-test",'
                '"message":{"role":"assistant","provider":"lmstudio",'
                '"model":"candidate","content":[{"type":"text","text":"done"},'
                '{"type":"toolCall","name":"write"}],'
                '"usage":{"input":40,"output":12,"cacheRead":3}}}\n',
                encoding="utf-8",
            )
            summary = parse_pi_jsonl(path)
            self.assertEqual(summary.events_seen, 1)
            self.assertEqual(summary.malformed_lines, 1)
            self.assertEqual(summary.session_id, "session-test")
            self.assertEqual(summary.provider_id, "lmstudio")
            self.assertEqual(summary.model_id, "candidate")
            self.assertEqual(summary.turns, 1)
            self.assertEqual(summary.tool_calls, 1)
            self.assertEqual(summary.usage["total_tokens"], 52)
            self.assertEqual(summary.final_message, "done")

    def test_pi_executor_materializes_scoped_config_and_admits_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            agent_dir = root / "scoped-home" / ".pi" / "agent"
            runner = _FakeRunner()
            context = HarnessExecutionContext(
                plan=InvocationPlan(
                    ("pi", "--mode", "json"),
                    model="candidate",
                    working_directory=str(workspace),
                ),
                workspace=workspace,
                evidence_root=root / "raw",
                prompt="build the artifact",
                environment={"PI_CODING_AGENT_DIR": str(agent_dir)},
                timeout_seconds=12,
                runner=runner,
                metadata={
                    "provider_settings": {
                        "native_name": "lmstudio",
                        "base_url": "http://127.0.0.1:1234/v1",
                    }
                },
            )
            recorder = EventRecorder()
            admission = InvocationAdmission(1, recorder)
            result = PiAttemptExecutor(context)(1, None, admission)
            self.assertTrue(admission.started)
            self.assertTrue(runner.calls[0]["prompt"].startswith("/wiggum "))
            self.assertEqual(result.terminal_reason, "process_exited")
            self.assertIsNone(result.candidate_path)
            self.assertEqual(len(result.raw_evidence_refs), 3)
            models = json.loads((agent_dir / "models.json").read_text(encoding="utf-8"))
            self.assertEqual(models["providers"]["lmstudio"]["baseUrl"], "http://127.0.0.1:1234/v1")
            summary = json.loads((root / "raw/pi-wiggum-attempt-001.summary.json").read_text())
            self.assertEqual(summary["usage"]["total_tokens"], 52)
            self.assertEqual(summary["tool_calls"], 1)


if __name__ == "__main__":
    unittest.main()
