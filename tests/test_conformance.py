from __future__ import annotations

import unittest

from ralph_bench.conformance import evaluate_public_conformance
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
        self.assertNotIn("threshold", str(result["failures"]).lower())


if __name__ == "__main__":
    unittest.main()
