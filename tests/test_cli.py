from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from ralph_bench.cli import Wizard, main
from ralph_bench.adapters import built_in_registry
from ralph_bench.adapters.contracts import ProbeContext, ProcessResult
from ralph_bench.experiments import load_experiment, parse_experiment, save_experiment
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

    def test_run_validates_and_honestly_declines_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.toml"
            save_experiment(parse_experiment(cloud_raw()), path)
            output = []
            self.assertEqual(
                main(
                    ["run", str(path)],
                    output_fn=output.append,
                    stdin=io.StringIO(),
                    probe_context=ProbeContext(process_runner=self.successful_process),
                ),
                3,
            )
            self.assertIn("not implemented", " ".join(output).lower())

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
                "",  # repetitions
                "",  # wall time
                "",  # attempts
                "",  # scenario
                "",  # inbox
                "20.00",
                "1",
                "",  # computed pool
                "",  # pool ID
                "chatgpt-plus",
                "",  # source
                "",  # rationale
                "2026-08-01",
                "2026-08-31",
                "",  # save
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
        main(
            ["doctor", "--json"],
            output_fn=output.append,
            stdin=io.StringIO(),
            probe_context=ProbeContext(process_runner=self.successful_process),
        )
        self.assertEqual(output[0][0], "{")

    def test_bundle_validate_and_build_skeleton_commands_are_registered(self):
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
        self.assertEqual(
            main(["build"], output_fn=output.append, stdin=io.StringIO()), 3
        )
        self.assertIn("not implemented", output[0].lower())

    def test_wizard_exposes_defaults_and_computes_subscription_pool(self):
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
                "2",
                "",  # scenario pack
                "",  # inbox
                "20.00",
                "0.25",
                "",  # accept computed pool
                "",  # pool id
                "chatgpt-plus",
                "",  # source
                "",  # rationale
                "2026-08-01",
                "2026-08-31",
                "",  # save confirmation
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
            self.assertEqual(experiment.cost.pool_cost_usd, "5.00")
            self.assertIn("Computed experiment pool: $5.00", "\n".join(output))


if __name__ == "__main__":
    unittest.main()
