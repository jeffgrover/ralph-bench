from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ralph_bench.browser_runtime import BrowserEvaluationArtifacts
from ralph_bench.conformance import (
    PUBLIC_SMOKE_SETTLE_MS,
    evaluate_public_conformance,
    load_public_smoke_scenario,
    run_conformance_evaluation,
)
from ralph_bench.gates import CarArrival, DemandStage, GateScenario, PedestrianArrival


def smoke_scenario() -> GateScenario:
    return GateScenario(
        "public-smoke",
        "public-smoke",
        0,
        2_000,
        (DemandStage("smoke", 0, 2_000, 0, 0, False, False),),
        (CarArrival("car-1", "north", "south", 0),),
        (PedestrianArrival("ped-1", "north", "east-to-west", 100),),
    )


class ConformanceTests(unittest.TestCase):
    def test_shared_runner_uses_caller_owned_output_and_evidence_paths(self):
        calls = []

        def evaluator(candidate, output, **kwargs):
            calls.append((candidate, output, kwargs))
            return BrowserEvaluationArtifacts(
                {"evaluation": {"outcome": "passed"}},
                output / "result.json",
                output / "overview.webm",
                output / "overview.png",
                output / "overview.json",
                kwargs["raw_evidence"] / "stdout.txt",
                kwargs["raw_evidence"] / "stderr.txt",
                0.1,
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "candidate"
            candidate.mkdir()
            output = root / "browser-output"
            raw = root / "raw"
            artifacts = run_conformance_evaluation(
                candidate,
                smoke_scenario(),
                output=output,
                raw_evidence=raw,
                chromium=root / "chromium",
                playwright_browsers_path=root / "browsers",
                browser_evaluator=evaluator,
            )

        self.assertEqual(artifacts.result["evaluation"]["outcome"], "passed")
        self.assertEqual(calls[0][0], candidate)
        self.assertEqual(calls[0][1], output)
        self.assertEqual(calls[0][2]["raw_evidence"], raw)

    def test_public_conformance_is_unscored_and_requires_both_traveler_shapes(self):
        scenario = smoke_scenario()
        result = evaluate_public_conformance(
            scenario,
            {
                "ready": True,
                "issued": [
                    {"kind": "car", "id": "car-1"},
                    {"kind": "pedestrian", "id": "ped-1"},
                ],
                "completions": [
                    {"kind": "car", "id": "car-1", "finish": "south"},
                    {"kind": "pedestrian", "id": "ped-1", "finish": None},
                ],
                "invalid": [],
            },
            ({"time_ms": 0, "outstanding_cars": 0},),
        )
        self.assertEqual(result["outcome"], "passed")
        self.assertFalse(result["performance_eligible"])
        self.assertEqual(result["capacity_curve"], [])
        self.assertFalse(result["recovery"]["attempted"])

    def test_public_conformance_reports_missing_service_without_private_values(self):
        scenario = smoke_scenario()
        result = evaluate_public_conformance(
            scenario,
            {
                "ready": True,
                "issued": [{"kind": "car", "id": "car-1"}],
                "completions": [],
                "invalid": [],
            },
            (),
        )
        self.assertEqual(result["outcome"], "failed")
        self.assertIn("traveler-service", {item["assertion_id"] for item in result["assertions"] if item["result"] == "fail"})
        self.assertIn("car-1", result["metrics"]["missing_traveler_ids"])
        self.assertNotIn("threshold", str(result["failures"]).lower())

    def test_checked_in_smoke_has_a_settle_window_after_the_last_arrival(self):
        scenario = load_public_smoke_scenario(
            Path(__file__).parents[1]
            / "challenges"
            / "busy-intersection"
            / "v1"
            / "public"
            / "scenario-pack.json"
        )
        latest_arrival = max(
            item.arrival_ms for item in (*scenario.cars, *scenario.pedestrians)
        )
        self.assertEqual(scenario.horizon_ms, latest_arrival + PUBLIC_SMOKE_SETTLE_MS)


if __name__ == "__main__":
    unittest.main()
