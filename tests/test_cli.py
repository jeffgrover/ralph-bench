from __future__ import annotations

import io
import json
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pathlib import Path

from ralph_bench.cli import Wizard, main
from ralph_bench.conductor import CompletedRun, EvaluationRunSummary
from ralph_bench.adapters import built_in_registry
from ralph_bench.adapters.contracts import ProbeContext, ProcessResult
from ralph_bench.experiments import (
    ExperimentError,
    load_experiment,
    parse_experiment,
    save_experiment,
)
from tests.test_experiments import cloud_raw


class CliTests(unittest.TestCase):
    @staticmethod
    def successful_process(argv, _timeout):
        if argv[-1] == "--version":
            return ProcessResult(0, "codex-cli 0.149.0\n")
        return ProcessResult(0, "Logged in using ChatGPT\n")

    def test_no_args_non_tty_never_prompts(self):
        output = []
        self.assertEqual(main([], output_fn=output.append, stdin=io.StringIO()), 2)
        self.assertIn("requires an interactive terminal", output[0])

    def test_run_executes_the_injected_conductor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.toml"
            save_experiment(parse_experiment(cloud_raw()), path)
            output = []
            calls = []

            def runner(experiment, sut, registry, *, output_fn):
                calls.append((experiment, sut, registry))
                return EvaluationRunSummary(
                    "exp-fixture",
                    (
                        CompletedRun(
                            "run-1",
                            1,
                            Path(directory) / "run-1.ralph.zip",
                            True,
                            "passed",
                            1,
                        ),
                    ),
                )

            self.assertEqual(
                main(
                    ["run", str(path)],
                    output_fn=output.append,
                    stdin=io.StringIO(),
                    probe_context=ProbeContext(process_runner=self.successful_process),
                    evaluation_runner=runner,
                ),
                0,
            )
            self.assertEqual(len(calls), 1)
            self.assertIn("produced 1", " ".join(output).lower())

    def test_zero_argument_flow_confirms_then_runs(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "guided.toml"
            answers = iter(
                (
                    "",  # client
                    "",  # provider
                    "",  # model
                    "",  # name
                    "",  # challenge
                    "",  # effort
                    "",  # independent runs
                    "",  # wall time
                    "",  # repairs
                    "",  # inbox
                    str(destination),
                    "yes",
                    "no",  # do not open the fixture preview
                )
            )
            prompts = []
            ran = []

            def runner(experiment, sut, registry, *, output_fn):
                ran.append(experiment)
                return EvaluationRunSummary(
                    "exp-fixture",
                    (
                        CompletedRun(
                            "run-1",
                            1,
                            Path(directory) / "run-1.ralph.zip",
                            False,
                            "failed",
                            1,
                        ),
                    ),
                )

            result = main(
                [],
                input_fn=lambda prompt: prompts.append(prompt) or next(answers),
                output_fn=lambda _message: None,
                stdin=Tty(),
                probe_context=ProbeContext(process_runner=self.successful_process),
                evaluation_runner=runner,
            )
            self.assertEqual(result, 0)
            self.assertEqual(len(ran), 1)
            self.assertTrue(destination.is_file())
            self.assertTrue(any("Run this evaluation now?" in item for item in prompts))
            self.assertIn("recorded simulation overview", prompts[-1])

    def test_zero_argument_flow_can_save_without_running(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "guided.toml"
            answers = iter(("", "", "", "", "", "", "", "", "", "", str(destination), "no"))
            ran = []
            output = []
            result = main(
                [],
                input_fn=lambda _prompt: next(answers),
                output_fn=output.append,
                stdin=Tty(),
                probe_context=ProbeContext(process_runner=self.successful_process),
                evaluation_runner=lambda *args, **kwargs: ran.append(True),
            )
            self.assertEqual(result, 0)
            self.assertFalse(ran)
            self.assertIn("not started", " ".join(output).lower())

    def test_zero_argument_final_confirmation_interrupt_preserves_saved_file(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True

        for interruption in (EOFError(), KeyboardInterrupt()):
            with self.subTest(interruption=type(interruption).__name__), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "guided.toml"
                answers = iter(
                    ("", "", "", "", "", "", "", "", "", "", str(destination))
                )
                ran: list[bool] = []
                output: list[str] = []

                def answer(prompt: str) -> str:
                    if prompt.startswith("Run this evaluation now?"):
                        raise interruption
                    return next(answers)

                result = main(
                    [],
                    input_fn=answer,
                    output_fn=output.append,
                    stdin=Tty(),
                    probe_context=ProbeContext(process_runner=self.successful_process),
                    evaluation_runner=lambda *args, **kwargs: ran.append(True),
                )
                self.assertEqual(result, 130)
                self.assertTrue(destination.is_file())
                self.assertFalse(ran)
                self.assertIn("remains saved", " ".join(output).lower())

    def test_repair_passes_are_limited_to_one_in_p0a(self):
        prompts: list[str] = []
        self.assertEqual(
            Wizard(
                input_fn=lambda prompt: prompts.append(prompt) or "1"
            )._ask_repair_passes(),
            1,
        )
        self.assertIn("Ralph repair passes per independent run", prompts[0])
        with self.assertRaisesRegex(ExperimentError, "cannot exceed 1"):
            Wizard(input_fn=lambda _prompt: "2")._ask_repair_passes()

    def test_wizard_cancel_does_not_create_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-created.toml"
            output = []
            wizard = Wizard(
                input_fn=lambda prompt: "cancel",
                output_fn=output.append,
                probe_context=ProbeContext(process_runner=self.successful_process),
            )
            self.assertEqual(wizard.run(), 130)
            self.assertFalse(path.exists())
            self.assertIn("no experiment file", " ".join(output).lower())

    def test_wizard_allows_a_manual_executable_for_registered_client(self):
        calls: list[tuple[str, ...]] = []

        def process(argv, _timeout):
            calls.append(argv)
            if argv[0] == "/opt/custom/codex" and argv[-1] == "--version":
                return ProcessResult(0, "codex-cli 0.149.0\n")
            if argv[0] == "/opt/custom/codex" and argv[1:] == ("login", "status"):
                return ProcessResult(0, "Logged in using ChatGPT\n")
            return ProcessResult(1, "", "not available")

        answers = iter(
            (
                "",  # registered client
                "/opt/custom/codex",
                "",  # provider
                "",  # model
                "",  # name
                "",  # challenge
                "",  # effort
                "",  # independent runs
                "",  # wall time
                "",  # Ralph repair passes
                "",  # inbox
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "manual-client.toml"
            wizard = Wizard(
                input_fn=lambda _prompt: next(answers),
                output_fn=lambda _message: None,
                probe_context=ProbeContext(process_runner=process),
            )
            self.assertEqual(wizard.run(destination), 0)
            self.assertEqual(
                load_experiment(destination).client_options.executable,
                "/opt/custom/codex",
            )
        self.assertIn(("/opt/custom/codex", "--version"), calls)
        self.assertIn(("/opt/custom/codex", "login", "status"), calls)

    def test_doctor_json_is_machine_readable(self):
        output = []
        with (
            patch(
                "ralph_bench.cli.find_chromium",
                return_value=Path("/usr/bin/chromium"),
            ),
            patch(
                "ralph_bench.cli.find_playwright_browsers_path",
                return_value=Path("/tmp/ms-playwright"),
            ),
        ):
            main(
                ["doctor", "--json"],
                output_fn=output.append,
                stdin=io.StringIO(),
                probe_context=ProbeContext(process_runner=self.successful_process),
            )
        self.assertEqual(output[0][0], "{")
        self.assertTrue(json.loads(output[0])["available"])

    def test_bundle_validate_and_build_commands_are_registered(self):
        output: list[str] = []
        self.assertEqual(
            main(
                ["bundle", "validate", "/definitely/missing.ralph.zip", "--json"],
                output_fn=output.append,
                stdin=io.StringIO(),
            ),
            1,
        )
        self.assertFalse(json.loads(output[0])["valid"])
        output.clear()
        with tempfile.TemporaryDirectory() as directory:
            output.clear()
            destination = Path(directory) / "site"
            self.assertEqual(
                main(
                    ["build", "--source", str(Path(directory) / "missing"), "--output", str(destination)],
                    output_fn=output.append,
                    stdin=io.StringIO(),
                ),
                0,
            )
            self.assertTrue((destination / "index.html").is_file())
            self.assertIn("0 valid bundle", output[0])

    def test_public_conformance_command_reports_machine_result(self):
        output: list[str] = []
        with patch(
            "ralph_bench.cli.run_public_conformance",
            return_value={
                "schema_version": "conformance/v1",
                "outcome": "failed",
                "passed": False,
                "assertions": [],
            },
        ) as check:
            result = main(
                ["conformance", "/tmp/candidate", "--json"],
                output_fn=output.append,
                stdin=io.StringIO(),
            )
        self.assertEqual(result, 1)
        self.assertEqual(json.loads(output[0])["outcome"], "failed")
        check.assert_called_once()

    def test_preview_command_opens_recorded_bundle_media(self):
        output: list[str] = []
        media = Path("/tmp/recorded-overview.webm")
        with patch(
            "ralph_bench.cli.open_bundle_preview",
            return_value=SimpleNamespace(media_path=media),
        ) as preview:
            result = main(
                ["preview", "/tmp/result.ralph.zip"],
                output_fn=output.append,
                stdin=io.StringIO(),
            )
        self.assertEqual(result, 0)
        preview.assert_called_once_with(Path("/tmp/result.ralph.zip"))
        self.assertIn(str(media), output[0])

    def test_wizard_derives_scenario_pack_and_omits_subscription_questionnaire(self):
        answers = iter(
            (
                "",  # client
                "",  # provider
                "",  # model
                "",  # name
                "",  # challenge
                "high",
                "3",
                "900",
                "1",  # Ralph repair pass -> max_attempts=2
                "",  # inbox
            )
        )
        output: list[str] = []
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "experiment.toml"
            wizard = Wizard(
                input_fn=lambda _prompt: next(answers),
                output_fn=output.append,
                registry=built_in_registry(),
                probe_context=ProbeContext(process_runner=self.successful_process),
            )
            self.assertEqual(wizard.run(destination), 0)
            experiment = load_experiment(destination)
            self.assertEqual(experiment.repetitions, 3)
            self.assertEqual(experiment.budget.max_wall_seconds, 900)
            self.assertEqual(experiment.budget.max_attempts, 2)
            self.assertEqual(
                experiment.evaluation.scenario_pack, "traffic-intersection-p0a"
            )
            self.assertIn(
                "Evaluation profile: traffic-intersection-p0a",
                "\n".join(output),
            )
            self.assertNotIn("subscription cost policy", "\n".join(output).lower())
            self.assertNotIn("billing-period cost", "\n".join(output).lower())
            self.assertIn(
                "Cost: subscription — per-run USD unavailable",
                "\n".join(output),
            )

    def test_zero_argument_wizard_uses_one_derived_save_prompt(self):
        answers = iter(
            (
                "",  # client
                "",  # provider
                "",  # model
                "",  # name -> codex-luna
                "",  # challenge
                "",  # effort
                "",  # independent runs
                "",  # wall time
                "",  # Ralph repair passes
                "",  # inbox
                "",  # derived experiment path
            )
        )
        prompts: list[str] = []
        output: list[str] = []

        def answer(prompt: str) -> str:
            prompts.append(prompt)
            return next(answers)

        wizard = Wizard(
            input_fn=answer,
            output_fn=output.append,
            registry=built_in_registry(),
            probe_context=ProbeContext(process_runner=self.successful_process),
        )
        with patch("ralph_bench.cli.save_experiment") as save:
            self.assertEqual(wizard.run(), 0)

        self.assertEqual(save.call_args.args[1], Path("experiments/codex-luna.toml"))
        save_prompts = [prompt for prompt in prompts if "save" in prompt.lower()]
        self.assertEqual(len(save_prompts), 1)
        self.assertNotIn("Save this experiment", "\n".join(prompts))
        rendered = "\n".join(output)
        self.assertNotIn("busy-intersection/v1 (busy-intersection/v1)", rendered)
        self.assertNotIn("medium (medium)", rendered)


if __name__ == "__main__":
    unittest.main()
