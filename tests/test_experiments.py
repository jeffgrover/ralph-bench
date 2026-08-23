from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ralph_bench.experiments import ExperimentError, load_experiment, parse_experiment, render_experiment, save_experiment


def cloud_raw(**overrides):
    value = {"schema_version": "experiment/v1", "name": "demo", "challenge": "busy-intersection/v1", "client": "codex-cli", "provider": "openai-chatgpt", "model": "gpt-5.6-luna", "track": "cloud-subscription"}
    value.update(overrides)
    return value


class ExperimentTests(unittest.TestCase):
    def test_unknown_field_is_specific_and_subscription_cost_is_optional(self):
        with self.assertRaisesRegex(ExperimentError, "unknown experiment field"):
            parse_experiment({**cloud_raw(), "surprise": True})
        experiment = parse_experiment({k: v for k, v in cloud_raw().items() if k != "cost"})
        self.assertNotIn("[cost]", render_experiment(experiment))

    def test_cost_table_is_rejected_in_p0a(self):
        with self.assertRaisesRegex(ExperimentError, "unknown experiment field.*cost"):
            parse_experiment({**cloud_raw(), "cost": {"status": "unavailable"}})

    def test_only_p0a_tracks_are_accepted(self):
        with self.assertRaisesRegex(ExperimentError, "unsupported track"):
            parse_experiment({**cloud_raw(), "track": "cloud-metered"})

    def test_challenge_and_scenario_profile_must_match(self):
        with self.assertRaisesRegex(ExperimentError, "not compatible"):
            parse_experiment(
                {
                    **cloud_raw(),
                    "evaluation": {"scenario_pack": "traffic-city-p0b"},
                }
            )
        with self.assertRaisesRegex(ExperimentError, "no scenario profile"):
            parse_experiment(
                {**cloud_raw(), "challenge": "five-by-five-rush/v1"}
            )

    def test_native_loop_cannot_request_ralph_repair_attempts(self):
        with self.assertRaisesRegex(ExperimentError, "must be 1.*native"):
            parse_experiment(
                {
                    **cloud_raw(),
                    "client_options": {"loop": "native"},
                }
            )
        experiment = parse_experiment(
            {
                **cloud_raw(),
                "client_options": {"loop": "native"},
                "budget": {"max_attempts": 1},
            }
        )
        self.assertEqual(experiment.budget.max_attempts, 1)

    def test_deterministic_round_trip_and_non_overwriting_atomic_save(self):
        experiment = parse_experiment(cloud_raw())
        self.assertEqual(render_experiment(experiment), render_experiment(experiment))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiment.toml"
            save_experiment(experiment, path)
            self.assertEqual(load_experiment(path), experiment)
            with self.assertRaises(FileExistsError):
                save_experiment(experiment, path)

    def test_explicit_client_executable_round_trips(self):
        raw = cloud_raw(
            client_options={
                "reasoning_effort": "high",
                "loop": "controlled",
                "executable": "/opt/codex/bin/codex",
            }
        )
        experiment = parse_experiment(raw)
        self.assertEqual(
            experiment.client_options.executable, "/opt/codex/bin/codex"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom-client.toml"
            save_experiment(experiment, path)
            self.assertEqual(load_experiment(path), experiment)
            self.assertIn(
                'executable = "/opt/codex/bin/codex"',
                path.read_text(encoding="utf-8"),
            )

    def test_toml_rendering_escapes_control_characters(self):
        experiment = parse_experiment({**cloud_raw(), "name": "line\r\ntab\tquoted\""})
        rendered = render_experiment(experiment)
        self.assertIn(r'line\r\ntab\tquoted\"', rendered)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "escaped.toml"
            save_experiment(experiment, path)
            self.assertEqual(load_experiment(path), experiment)

    def test_whitespace_only_identity_is_rejected(self):
        with self.assertRaisesRegex(ExperimentError, "name must be a non-empty string"):
            parse_experiment({**cloud_raw(), "name": "   "})


if __name__ == "__main__":
    unittest.main()
