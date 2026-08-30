from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import patch

from ralph_bench.adapters import (
    LMStudioProviderAdapter,
    PiHarnessAdapter,
    built_in_registry,
    resolve_sut,
)
from ralph_bench.adapters.codex import CodexHarnessAdapter
from ralph_bench.adapters.contracts import ProbeContext, ProcessResult
from ralph_bench.browser_runtime import BrowserEvaluationArtifacts
from ralph_bench.bundles import validate_bundle
from ralph_bench.capture_validation import PNG_SIGNATURE, WEBM_EBML_SIGNATURE
from ralph_bench.conductor import (
    ProgressReporter,
    _AttemptProgress,
    _attempt_status,
    _interactive_check_loop,
    execute_experiment,
)
from ralph_bench.events import EventRecorder
from ralph_bench.execution import HarnessAttemptResult, InvocationAdmission
from ralph_bench.experiments import parse_experiment
from tests.test_experiments import cloud_raw


class _FakeCodexExecutor:
    def __init__(self, *, workspace, evidence_root, prompt, **_kwargs):
        self.workspace = Path(workspace)
        self.evidence_root = Path(evidence_root)
        self.prompt = prompt

    def __call__(self, attempt_number, feedback, admission):
        self.prompt(attempt_number, feedback)
        fixture = (
            Path(__file__).parent
            / "fixtures"
            / "busy_intersection"
            / "passing"
            / "index.html"
        )
        shutil.copyfile(fixture, self.workspace / "index.html")
        stdout = self.evidence_root / "codex-attempt-001.jsonl"
        stderr = self.evidence_root / "codex-attempt-001.stderr.txt"
        summary = self.evidence_root / "codex-attempt-001.summary.json"
        stdout.write_text('{"type":"thread.started","thread_id":"fixture"}\n')
        stderr.write_text("")
        summary.write_text(
            json.dumps(
                {
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "total_tokens": 15,
                        "reasoning_tokens": 1,
                        "cache_read_tokens": 0,
                    },
                    "turns": 1,
                }
            )
        )
        admission.admit(
            process_spawned=True,
            prompt_provided=True,
            evidence_ref="events/raw/codex-attempt-001.jsonl",
        )
        return HarnessAttemptResult(
            self.workspace,
            "process_exited",
            (
                "events/raw/codex-attempt-001.jsonl",
                "events/raw/codex-attempt-001.stderr.txt",
                "events/raw/codex-attempt-001.summary.json",
            ),
        )


def _fake_executor_factory(context):
    return _FakeCodexExecutor(
        workspace=context.workspace,
        evidence_root=context.evidence_root,
        prompt=context.prompt,
    )


def _fake_browser(candidate, output, *, raw_evidence, **_kwargs):
    seed = _kwargs.get("seed", 17)
    output.mkdir()
    raw_evidence.mkdir(exist_ok=True)
    capture = {
        "schema_version": "capture/v1",
        "viewport": {"width": 1440, "height": 900},
        "scenario_id": "busy-intersection-gates-balanced",
        "scenario_profile": "balanced-gates",
        "seed": seed,
        "simulated_horizon_ms": 50000,
        "simulation_interval_ms": {"start": 0, "end": 50000, "step": 250},
        "simulation_phase": "gates-load-and-capture",
        "playback_step_ms": 250,
        "playback_delay_ms": 250,
        "playback_rate": 1,
        "duration_ms": 50000,
        "frame_rate_fps": 25,
        "capture_worker": {
            "id": "fixture",
            "protocol": "browser-worker/v1",
            "version": "1",
        },
        "browser": "chromium",
        "browser_version": "fixture",
        "playwright_version": "fixture",
    }
    result = {
        "schema_version": "browser-evaluation/v2",
        "protocol": "gates/v1",
        "evaluation": {
            "scenario_id": "busy-intersection-gates-balanced",
            "seed": seed,
            "outcome": "passed",
            "measurement_status": "measured",
            "metrics": {"peak_monitored_throughput": 900},
            "recovery": {"passed": True},
            "failures": [],
            "assertions": [],
            "capacity_curve": [],
            "runtime_observations": [],
        },
        "scenario": {
            "scenario_id": "busy-intersection-gates-balanced",
            "profile": "balanced-gates",
            "seed": seed,
        },
        "monitor": {"api_version": "gates/v1", "ready": True},
        "browser": {"name": "fixture"},
        "capture": capture,
    }
    result_path = output / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    metadata = output / "overview.json"
    metadata.write_text(json.dumps(capture), encoding="utf-8")
    video = output / "overview.webm"
    poster = output / "overview.png"
    video.write_bytes(WEBM_EBML_SIGNATURE + b"\x42\x82\x84webm")
    poster.write_bytes(
        PNG_SIGNATURE
        + b"\x00\x00\x00\rIHDR"
        + (1440).to_bytes(4, "big")
        + (900).to_bytes(4, "big")
    )
    stdout = raw_evidence / "browser-worker.stdout.txt"
    stderr = raw_evidence / "browser-worker.stderr.txt"
    stdout.write_text("")
    stderr.write_text("")
    return BrowserEvaluationArtifacts(
        result,
        result_path,
        video,
        poster,
        metadata,
        stdout,
        stderr,
        0.1,
    )


class ConductorTests(unittest.TestCase):
    @staticmethod
    def _probe(argv, _timeout):
        if argv[-1] == "--version":
            return ProcessResult(0, "codex-cli 0.149.0\n")
        return ProcessResult(0, "Logged in using ChatGPT\n")

    def test_fixture_run_crosses_every_p0a_boundary_and_validates_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = cloud_raw()
            raw["repetitions"] = 1
            raw["budget"] = {"max_wall_seconds": 60, "max_attempts": 1}
            raw["output"] = {"inbox": str(root / "inbox")}
            experiment = parse_experiment(raw)
            executable = root / "codex"
            executable.write_text("fixture")
            executable.chmod(0o700)
            auth = root / "auth.json"
            auth.write_text("{}")
            registry = built_in_registry(
                codex=CodexHarnessAdapter(
                    executable=str(executable),
                    attempt_executor_factory=_fake_executor_factory,
                    credential_reference_factory=lambda: auth,
                )
            )
            sut = resolve_sut(
                experiment,
                registry,
                context=ProbeContext(process_runner=self._probe),
            )
            output: list[str] = []
            with (
                patch(
                    "ralph_bench.conductor.find_chromium",
                    return_value=root / "chromium",
                ),
                patch(
                    "ralph_bench.conductor.find_playwright_browsers_path",
                    return_value=root / "playwright",
                ),
                patch(
                    "ralph_bench.conductor.run_browser_evaluation",
                    side_effect=_fake_browser,
                ),
            ):
                summary = execute_experiment(
                    experiment,
                    sut,
                    registry,
                    output_fn=output.append,
                    probe_context=ProbeContext(process_runner=self._probe),
                )
            self.assertEqual(len(summary.runs), 1)
            validation = validate_bundle(summary.runs[0].bundle)
            self.assertTrue(
                validation.valid,
                [(item.code, item.path, item.detail) for item in validation.diagnostics],
            )
            with zipfile.ZipFile(summary.runs[0].bundle) as archive:
                preflight = json.loads(
                    archive.read("provenance/toolchain-preflight.json")
                )
            self.assertEqual(preflight["schema_version"], "toolchain-preflight/v1")
            self.assertEqual(preflight["status"], "ready")
            rendered = "\n".join(output)
            self.assertIn("starting initial model attempt", rendered)
            self.assertIn("public artifact checks passed", rendered)
            self.assertIn("recording the overview", rendered)
            self.assertIn("bundle saved", rendered)

    def test_preflight_failure_stops_before_any_bundle_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = cloud_raw()
            raw["output"] = {"inbox": str(root / "inbox")}
            experiment = parse_experiment(raw)
            registry = built_in_registry()
            sut = resolve_sut(
                experiment,
                registry,
                context=ProbeContext(process_runner=self._probe),
            )

            def failed(_argv, _timeout):
                return ProcessResult(1, "", "update unavailable")

            with self.assertRaisesRegex(Exception, "preflight"):
                execute_experiment(
                    experiment,
                    sut,
                    registry,
                    output_fn=lambda _message: None,
                    probe_context=ProbeContext(process_runner=failed),
                )
            self.assertFalse((root / "inbox").exists())

    def test_local_pi_composition_uses_harness_factory_without_conductor_branch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pi_binary = root / "pi"
            pi_binary.write_text("fixture")
            pi_binary.chmod(0o700)
            raw = cloud_raw(
                name="local-pi",
                client="pi",
                provider="lm-studio",
                model="local-model",
                track="local",
                client_options={"loop": "native", "reasoning_effort": "medium"},
                budget={"max_wall_seconds": 60, "max_attempts": 1},
                output={"inbox": str(root / "inbox")},
            )
            experiment = parse_experiment(raw)

            def process(argv, _timeout):
                if argv[0] == str(pi_binary):
                    if argv[1:] == ("--version",):
                        return ProcessResult(0, "0.84.4\n")
                    if argv[1:] == ("list", "--no-approve"):
                        return ProcessResult(0, "npm:pi-wiggum\nnpm:pi-subagents\n")
                    return ProcessResult(0, "updated\n")
                if argv[1:] == ("--version",):
                    return ProcessResult(0, "CLI commit: fixture\n")
                if argv[1:4] == ("server", "status", "--json"):
                    return ProcessResult(0, '{"status":"running"}\n')
                if argv[1:5] == ("runtime", "update", "--all", "--yes"):
                    return ProcessResult(0, "runtime is current\n")
                if argv[1:] == ("ls", "--llm", "--json"):
                    return ProcessResult(0, '{"models":[{"modelKey":"local-model"}]}\n')
                if argv[1:] == ("ps", "--json"):
                    return ProcessResult(0, '{"models":[{"id":"local-model"}]}\n')
                return ProcessResult(1, "", "unexpected command")

            registry = built_in_registry(
                pi=PiHarnessAdapter(
                    executable=str(pi_binary),
                    process_runner=process,
                    attempt_executor_factory=_fake_executor_factory,
                    extension_root=root / "missing-pi-wiggum",
                ),
                lmstudio=LMStudioProviderAdapter(process_runner=process),
            )
            sut = resolve_sut(
                experiment,
                registry,
                context=ProbeContext(process_runner=process),
            )
            with (
                patch("ralph_bench.conductor.find_chromium", return_value=root / "chromium"),
                patch(
                    "ralph_bench.conductor.find_playwright_browsers_path",
                    return_value=root / "playwright",
                ),
                patch("ralph_bench.conductor.run_browser_evaluation", side_effect=_fake_browser),
            ):
                summary = execute_experiment(
                    experiment,
                    sut,
                    registry,
                    output_fn=lambda _message: None,
                    probe_context=ProbeContext(process_runner=process),
                )
            self.assertEqual(len(summary.runs), 1)
            self.assertTrue(validate_bundle(summary.runs[0].bundle).valid)

    def test_progress_timestamp_and_heartbeat_are_low_noise(self):
        ticks = iter((100.0, 165.4))
        timestamped: list[str] = []
        ProgressReporter(timestamped.append, clock=lambda: next(ticks)).emit("phase")
        self.assertEqual(timestamped, ["[rb 01:05] phase"])

        released = threading.Event()
        output: list[str] = []

        def write(message: str) -> None:
            output.append(message)
            if "still running" in message:
                released.set()

        def executor(_attempt, _feedback, _admission):
            self.assertTrue(released.wait(timeout=1))
            return HarnessAttemptResult(None, "process_exited")

        wrapped = _AttemptProgress(
            executor,
            ProgressReporter(write),
            repetition=1,
            repetitions=1,
            attempts=2,
            remaining=lambda: 42,
            heartbeat_seconds=0.001,
        )
        wrapped(1, None, InvocationAdmission(1, EventRecorder()))
        messages_at_return = len(output)
        threading.Event().wait(0.01)
        self.assertEqual(len(output), messages_at_return)
        self.assertEqual(sum("still running" in item for item in output), 1)
        self.assertIn("starting initial model attempt 1/2", "\n".join(output))
        self.assertIn("model attempt 1 finished", "\n".join(output))

    def test_local_attempt_check_summarizes_structure_without_model_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw"
            workspace = root / "workspace"
            raw.mkdir()
            workspace.mkdir()
            (workspace / "index.html").write_text("<h1>secret prose</h1>")
            (raw / "codex-attempt-001.stderr.txt").write_text("")
            (raw / "codex-attempt-001.jsonl").write_text(
                "\n".join(
                    (
                        json.dumps({"type": "thread.started"}),
                        json.dumps(
                            {
                                "type": "item.completed",
                                "item": {
                                    "type": "command_execution",
                                    "status": "completed",
                                    "aggregated_output": "private model content",
                                },
                            }
                        ),
                    )
                )
                + "\n"
            )
            status = _attempt_status(raw, workspace, 1)
            self.assertIn("2 events", status)
            self.assertIn("1 tool command(s) completed", status)
            self.assertIn("workspace 1 file(s)", status)
            self.assertNotIn("private model content", status)
            self.assertNotIn("secret prose", status)

    @unittest.skipUnless(os.name == "posix", "PTY test is POSIX-specific")
    def test_interactive_check_loop_accepts_one_key_without_enter(self):
        master, slave = os.openpty()
        stop = threading.Event()
        checked = threading.Event()
        ready = threading.Event()
        stream = os.fdopen(slave, "r", encoding="utf-8")
        thread = threading.Thread(
            target=_interactive_check_loop,
            args=(stream, stop, checked.set, ready),
            daemon=True,
        )
        try:
            thread.start()
            self.assertTrue(ready.wait(timeout=1))
            os.write(master, b"c")
            self.assertTrue(checked.wait(timeout=1))
        finally:
            stop.set()
            thread.join(timeout=1)
            stream.close()
            os.close(master)


if __name__ == "__main__":
    unittest.main()
