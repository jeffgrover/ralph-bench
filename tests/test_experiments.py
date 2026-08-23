from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ralph_bench.experiments import ExperimentError, load_experiment, parse_experiment, render_experiment, save_experiment


def cloud_raw(**overrides):
    value = {"schema_version": "experiment/v1", "name": "demo", "challenge": "busy-intersection/v1", "client": "codex-cli", "provider": "openai-chatgpt", "model": "gpt-5.6-luna", "track": "cloud-subscription", "cost": {"policy": "flat-subscription-attempt-pool/v1", "pool_id": "pool", "pool_scope": "experiment", "currency": "USD", "service_plan": "chatgpt-plus", "billing_period_cost_usd": "20.00", "benchmark_allocation_fraction": "1.0", "pool_cost_usd": "20.00", "pool_cost_source": "operator_attested_period_charge", "allocation_rationale": "pilot", "billing_period_start": "2026-08-01", "billing_period_end": "2026-08-31", "closure": "all_expected_runs_terminal"}}
    value.update(overrides)
    return value


class ExperimentTests(unittest.TestCase):
    def test_unknown_field_and_missing_cloud_cost_are_specific(self):
        with self.assertRaisesRegex(ExperimentError, "unknown experiment field"):
            parse_experiment({**cloud_raw(), "surprise": True})
        with self.assertRaisesRegex(ExperimentError, "require.*cost"):
            parse_experiment({k: v for k, v in cloud_raw().items() if k != "cost"})

    def test_shared_cost_declaration_rejects_edges_and_accepts_explicit_zero(self):
        for field, value in (("benchmark_allocation_fraction", "NaN"), ("benchmark_allocation_fraction", "1.1"), ("pool_cost_usd", "19.99")):
            bad = cloud_raw()
            bad["cost"] = {**bad["cost"], field: value}
            with self.assertRaisesRegex(ExperimentError, "invalid cost declaration"):
                parse_experiment(bad)
        zero = cloud_raw()
        zero["cost"] = {**zero["cost"], "billing_period_cost_usd": "0", "benchmark_allocation_fraction": "0", "pool_cost_usd": "0", "zero_cost_evidence": "free plan attested"}
        self.assertEqual(parse_experiment(zero).cost.pool_cost_usd, "0.00")

    def test_cloud_metered_and_flat_subscription_are_not_combined(self):
        with self.assertRaisesRegex(ExperimentError, "cloud-metered"):
            parse_experiment({**cloud_raw(), "track": "cloud-metered"})

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
