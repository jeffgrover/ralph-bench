from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ralph_bench.challenge_adapters import (
    ChallengeAdapterError,
    ChallengeRegistry,
    ChallengeRun,
)


class FutureCityFixtureAdapter:
    """A protocol/topology-agnostic fixture for the challenge boundary."""

    challenge_id = "fixture/future-city/v1"

    def seed_for_repetition(self, repetition: int) -> int:
        return repetition * 101

    def prepare(self, project_root: Path, scenario_pack: str, seed: int) -> ChallengeRun:
        source = Path(project_root) / "public"
        return ChallengeRun(
            self.challenge_id,
            scenario_pack,
            seed,
            {"topology": "future-defined", "protocol": "city/v1"},
            "future-city-fixture",
            "future-city-profile",
            {"topology": "future-defined"},
            {"challenge_id": self.challenge_id, "protocol": "city/v1"},
            source,
        )


class ChallengeAdapterTests(unittest.TestCase):
    def test_registry_and_run_boundary_accept_future_protocol_and_topology(self):
        adapter = FutureCityFixtureAdapter()
        registry = ChallengeRegistry({adapter.challenge_id: adapter})
        with tempfile.TemporaryDirectory() as directory:
            run = registry.get(adapter.challenge_id).prepare(
                Path(directory), "future-city-pack", 303
            )
        self.assertEqual(run.scenario_id, "future-city-fixture")
        self.assertEqual(run.scenario["protocol"], "city/v1")
        self.assertEqual(run.scenario["topology"], "future-defined")

    def test_registry_rejects_unknown_challenge_without_busy_fallback(self):
        registry = ChallengeRegistry({})
        with self.assertRaisesRegex(ChallengeAdapterError, "unknown challenge"):
            registry.get("future-city/v1")


if __name__ == "__main__":
    unittest.main()
