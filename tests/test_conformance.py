from __future__ import annotations

from pathlib import Path
import unittest

from ralph_bench.conformance import (
    PUBLIC_SMOKE_SETTLE_MS,
    evaluate_public_conformance,
    load_public_smoke_scenario,
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
