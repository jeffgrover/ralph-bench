from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ralph_bench.gate_bridge import GATES_INIT_SCRIPT
from ralph_bench.gate_evaluator import check_static_candidate, evaluate_gate_monitor
from ralph_bench.gates import (
    CarArrival,
    DemandStage,
    GateScenario,
    PedestrianArrival,
)


def small_scenario() -> GateScenario:
    return GateScenario(
        "fixture-gates",
        "fixture",
        1,
        3_000,
        (
            DemandStage("warmup", 0, 1_000, 60, 60),
            DemandStage("load", 1_000, 2_000, 120, 0),
            DemandStage("cooldown", 2_000, 3_000, 0, 0, False, True),
        ),
        (
            CarArrival("car-1", "north", "south", 0),
            CarArrival("car-2", "east", "west", 1_100),
        ),
        (PedestrianArrival("ped-1", "north", "east-to-west", 100),),
    )


def issued(scenario: GateScenario) -> list[dict[str, object]]:
    return [
        {"kind": "car", "id": item.id, "issued_ms": item.arrival_ms}
        for item in scenario.cars
    ] + [
        {"kind": "pedestrian", "id": item.id, "issued_ms": item.arrival_ms}
        for item in scenario.pedestrians
    ]


class GateEvaluatorTests(unittest.TestCase):
    def test_minimal_monitor_produces_throughput_backlog_and_recovery(self) -> None:
        scenario = small_scenario()
        monitor = {
            "ready": True,
            "issued": issued(scenario),
            "completions": [
                {"kind": "car", "id": "car-1", "finish": "south", "completed_ms": 700, "latency_ms": 700},
                {"kind": "pedestrian", "id": "ped-1", "finish": None, "completed_ms": 800, "latency_ms": 700},
                {"kind": "car", "id": "car-2", "finish": "west", "completed_ms": 2_400, "latency_ms": 1_300},
            ],
            "invalid": [],
        }
        observations = (
            {"time_ms": 0, "outstanding_cars": 1},
            {"time_ms": 1_000, "outstanding_cars": 0},
            {"time_ms": 2_000, "outstanding_cars": 1},
            {"time_ms": 3_000, "outstanding_cars": 0},
        )
        result = evaluate_gate_monitor(scenario, monitor, observations)
        self.assertTrue(result.passed, result.to_dict())
        self.assertEqual(result.measurement_status, "measured")
        self.assertEqual(result.metrics["completed_cars"], 2)
        self.assertTrue(result.recovery.passed)
        self.assertGreater(result.metrics["peak_monitored_throughput"], 0)

    def test_missing_callbacks_are_unmeasurable_not_zero_throughput(self) -> None:
        scenario = small_scenario()
        result = evaluate_gate_monitor(
            scenario,
            {"ready": False, "issued": [], "completions": [], "invalid": []},
            (),
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.measurement_status, "unmeasurable")
        self.assertIn(
            "gates-interface-ready",
            {item.assertion_id for item in result.assertions if item.result == "fail"},
        )
        self.assertFalse(result.performance_eligible)

    def test_overloaded_working_artifact_fails_performance_but_remains_eligible(self) -> None:
        scenario = small_scenario()
        monitor = {
            "ready": True,
            "issued": issued(scenario),
            "completions": [
                {"kind": "car", "id": "car-1", "finish": "south", "completed_ms": 700, "latency_ms": 700},
                {"kind": "pedestrian", "id": "ped-1", "finish": None, "completed_ms": 800, "latency_ms": 700},
            ],
            "invalid": [],
        }
        observations = (
            {"time_ms": 0, "outstanding_cars": 0},
            {"time_ms": 1_000, "outstanding_cars": 0},
            {"time_ms": 2_000, "outstanding_cars": 2},
            {"time_ms": 3_000, "outstanding_cars": 2},
        )
        result = evaluate_gate_monitor(scenario, monitor, observations)
        self.assertFalse(result.passed)
        self.assertTrue(result.performance_eligible)
        self.assertEqual(result.measurement_status, "measured")
        self.assertIn(
            "capacity:load:completion-ratio",
            {item.code for item in result.failures},
        )
        self.assertIn("cooldown-recovery", {item.code for item in result.failures})

    def test_invalid_finish_notification_fails_integrity(self) -> None:
        scenario = small_scenario()
        result = evaluate_gate_monitor(
            scenario,
            {
                "ready": True,
                "issued": issued(scenario),
                "completions": [],
                "invalid": [{"code": "wrong-finish-gate", "id": "car-1"}],
            },
            ({"time_ms": 3_000, "outstanding_cars": 2},),
        )
        self.assertFalse(result.passed)
        self.assertIn(
            "completion-integrity",
            {item.assertion_id for item in result.assertions if item.result == "fail"},
        )

    def test_static_check_accepts_css_custom_property_and_rejects_real_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text(
                '<style>:root{--ws:64px}</style><script>RalphGates.register({carArrived(){},pedestrianArrived(){}})</script>',
                encoding="utf-8",
            )
            self.assertTrue(check_static_candidate(root).passed)
            (root / "index.html").write_text(
                '<script src="https://example.invalid/app.js"></script>',
                encoding="utf-8",
            )
            self.assertFalse(check_static_candidate(root).passed)

    def test_checked_in_fixtures_cover_green_and_broken_paths(self) -> None:
        fixtures = Path(__file__).parent / "fixtures" / "busy_intersection"
        self.assertTrue(check_static_candidate(fixtures / "passing").passed)
        self.assertFalse(check_static_candidate(fixtures / "broken").passed)

    def test_static_check_allows_aliasing_the_injected_gate_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text(
                "<script>const gates = globalThis.RalphGates; "
                "gates.register({carArrived(){}, pedestrianArrived(){}});</script>",
                encoding="utf-8",
            )
            result = check_static_candidate(root)
        self.assertTrue(result.passed, result.to_dict())

    def test_injected_library_exposes_only_the_small_public_surface(self) -> None:
        self.assertIn('apiVersion: "gates/v1"', GATES_INIT_SCRIPT)
        self.assertIn("carArrived", GATES_INIT_SCRIPT)
        self.assertIn("pedestrianArrived", GATES_INIT_SCRIPT)
        self.assertNotIn("describeNetwork", GATES_INIT_SCRIPT)
        self.assertNotIn("drainEvents", GATES_INIT_SCRIPT)
        self.assertNotIn("await handler(", GATES_INIT_SCRIPT)
        self.assertIn("result.catch", GATES_INIT_SCRIPT)


if __name__ == "__main__":
    unittest.main()
