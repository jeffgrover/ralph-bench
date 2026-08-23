from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ralph_bench.traffic import (
    DemandStage,
    PedestrianRequest,
    Scenario,
    TrafficEvent,
    TrafficSnapshot,
    TripObservation,
    VehicleObservation,
    VehicleTrip,
    busy_intersection_network,
    balanced_seed_for_repetition,
    build_balanced_scenario,
)
from ralph_bench.traffic_evaluator import (
    evaluate_observations,
    evaluate_transport,
    check_static_candidate,
)


def small_scenario(seed: int = 1) -> Scenario:
    stages = (
        DemandStage("load", 0, 1_000, 3_600),
        DemandStage("cooldown", 1_000, 2_000, 0, 0, False, True),
    )
    network = busy_intersection_network()
    movement = network.movements[0]
    return Scenario(
        "fixture",
        "balanced",
        seed,
        2_000,
        stages,
        (VehicleTrip("trip-1", movement.origin, movement.destination, movement.id, 0),),
        (PedestrianRequest("ped-1", network.crossings[0].id, 0),),
    )


class EvaluatorTests(unittest.TestCase):
    def test_lifecycle_only_completion_cannot_pass(self) -> None:
        scenario = small_scenario()
        snapshots = (
            TrafficSnapshot(0, trips=(TripObservation("trip-1", "requested"),)),
            TrafficSnapshot(900, trips=(TripObservation("trip-1", "completed"),)),
            TrafficSnapshot(1_500, trips=(TripObservation("trip-1", "completed"),)),
        )
        events = (TrafficEvent(1, 100, "trip.admitted", "trip-1"), TrafficEvent(2, 900, "trip.completed", "trip-1"))
        result = evaluate_observations(scenario, busy_intersection_network(), snapshots, events)
        self.assertFalse(result.passed)
        self.assertIn("physical-trip-lifecycle", {item.assertion_id for item in result.assertions if item.result == "fail"})

    def test_candidate_network_is_authoritative_evidence_only(self) -> None:
        scenario = small_scenario()
        expected = busy_intersection_network()
        described = expected.to_dict()
        described["lane_segments"][0]["speed_limit_mps"] = 100
        result = evaluate_observations(scenario, expected, (), (), candidate_network=described)
        failed = {item.assertion_id for item in result.assertions if item.result == "fail"}
        self.assertIn("network-compatibility", failed)
        self.assertEqual(result.outcome, "failed")

    def test_malformed_network_is_critical_even_when_observations_are_green(self) -> None:
        result = evaluate_observations(small_scenario(), busy_intersection_network(), (), (), candidate_network_error="malformed describeNetwork")
        failures = [item for item in result.assertions if item.assertion_id == "network-compatibility" and item.result == "fail"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].severity, "critical")

    def test_event_before_request_and_reversed_event_time_are_rejected(self) -> None:
        base = small_scenario()
        trip = base.trips[0]
        scenario = Scenario(base.scenario_id, base.profile, base.seed, base.horizon_ms, base.stages, (VehicleTrip(trip.trip_id, trip.origin, trip.destination, trip.movement_id, 100),), base.pedestrians)
        result = evaluate_observations(
            scenario,
            busy_intersection_network(),
            (),
            (TrafficEvent(2, 100, "trip.completed", "trip-1"), TrafficEvent(1, 0, "trip.admitted", "trip-1")),
        )
        failed = {item.assertion_id for item in result.assertions if item.result == "fail"}
        self.assertIn("event-order", failed)
        self.assertIn("event-request-time", failed)

    def test_original_observation_order_is_checked_before_aggregation(self) -> None:
        scenario = small_scenario()
        result = evaluate_observations(
            scenario,
            busy_intersection_network(),
            (TrafficSnapshot(900), TrafficSnapshot(0)),
            (),
        )
        self.assertIn("snapshot-time-monotonic", {item.assertion_id for item in result.assertions if item.result == "fail"})

    def test_seed_repetition_mapping_is_declared_and_recorded(self) -> None:
        self.assertEqual([balanced_seed_for_repetition(i) for i in (1, 2, 3, 4)], [17, 29, 43, 17])
        self.assertEqual(build_balanced_scenario(29).seed, 29)

    def test_passing_cohorts_are_bounded_for_all_public_seeds(self) -> None:
        for seed in (17, 29, 43):
            scenario = small_scenario(seed)
            movement = busy_intersection_network().movements[0]
            snapshots = (
                TrafficSnapshot(0, trips=(TripObservation("trip-1", "requested"),)),
                TrafficSnapshot(500, vehicles=(VehicleObservation("trip-1", movement.id, movement.lane_segments[0], 5, 2),), trips=(TripObservation("trip-1", "active"),)),
                TrafficSnapshot(900, vehicles=(VehicleObservation("trip-1", movement.id, movement.lane_segments[1], 55, 0, status="exited"),), trips=(TripObservation("trip-1", "completed"),)),
                TrafficSnapshot(1_500, trips=(TripObservation("trip-1", "completed"),)),
            )
            events = (
                TrafficEvent(1, 100, "trip.admitted", "trip-1"),
                TrafficEvent(2, 100, "vehicle.entered", "trip-1"),
                TrafficEvent(3, 900, "vehicle.exited", "trip-1"),
                TrafficEvent(4, 900, "trip.completed", "trip-1"),
            )
            result = evaluate_observations(scenario, busy_intersection_network(), snapshots, events)
            self.assertTrue(result.passed, (seed, result.to_dict()))
            for stage in result.capacity_curve:
                self.assertLessEqual(stage.admitted, stage.requested, (seed, stage.to_dict()))
                self.assertLessEqual(stage.completed, stage.requested, (seed, stage.to_dict()))
            cooldown = result.capacity_curve[-1]
            self.assertEqual((cooldown.requested, cooldown.admitted, cooldown.completed), (0, 0, 0))
    def test_passing_observations_reconcile_and_recover(self) -> None:
        scenario = small_scenario()
        events = (
            TrafficEvent(1, 100, "trip.admitted", "trip-1"),
            TrafficEvent(2, 100, "vehicle.entered", "trip-1"),
            TrafficEvent(3, 900, "vehicle.exited", "trip-1"),
            TrafficEvent(4, 900, "trip.completed", "trip-1"),
        )
        movement = busy_intersection_network().movements[0]
        snapshots = (
            TrafficSnapshot(0, trips=(TripObservation("trip-1", "requested"),)),
            TrafficSnapshot(500, vehicles=(VehicleObservation("trip-1", movement.id, movement.lane_segments[0], 10, 2),), trips=(TripObservation("trip-1", "active"),)),
            TrafficSnapshot(900, vehicles=(VehicleObservation("trip-1", movement.id, movement.lane_segments[1], 100, 0, status="exited"),), trips=(TripObservation("trip-1", "completed"),)),
            TrafficSnapshot(1_500, trips=(TripObservation("trip-1", "completed"),)),
        )
        result = evaluate_observations(scenario, busy_intersection_network(), snapshots, events)
        self.assertTrue(result.passed, result.to_dict())
        self.assertEqual(result.metrics["completed"], 1)
        self.assertTrue(result.recovery.passed)

    def test_collision_and_red_entry_are_critical_failures(self) -> None:
        scenario = small_scenario()
        movement = busy_intersection_network().movements[0]
        snapshots = (
            TrafficSnapshot(
                900,
                vehicles=(
                    # Same lane and position deliberately overlap.
                    VehicleObservation("trip-1", movement.id, movement.lane_segments[0], 20, 0, entered_on_red=True),
                    VehicleObservation("trip-2", movement.id, movement.lane_segments[0], 20, 0),
                ),
                trips=(TripObservation("trip-1", "active"),),
            ),
        )
        result = evaluate_observations(scenario, busy_intersection_network(), snapshots, ())
        failed = {item.assertion_id for item in result.assertions if item.result == "fail"}
        self.assertIn("no-overlap", failed)
        self.assertIn("no-red-entry", failed)
        self.assertEqual(result.outcome, "failed")

    def test_static_candidate_requires_offline_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text(
                '<script>window.__RALPH_BENCH__={apiVersion:"traffic/v1"};</script>',
                encoding="utf-8",
            )
            self.assertTrue(check_static_candidate(root).passed)
            (root / "index.html").write_text(
                '<script src="https://example.invalid/app.js"></script>',
                encoding="utf-8",
            )
            self.assertFalse(check_static_candidate(root).passed)

    def test_checked_in_fixture_artifacts_cover_green_and_broken_paths(self) -> None:
        fixtures = Path(__file__).parent / "fixtures" / "busy_intersection"
        self.assertTrue(check_static_candidate(fixtures / "passing").passed)
        self.assertFalse(check_static_candidate(fixtures / "broken").passed)

    def test_transport_boundary_is_injectable(self) -> None:
        scenario = small_scenario()

        class FakeTransport:
            def __init__(self) -> None:
                self.time = 0
                self.loaded = None
                self.emitted = False

            def load_scenario(self, scenario_payload):
                self.loaded = scenario_payload

            def reset(self, seed):
                self.time = 0
                self.emitted = False

            def advance(self, simulated_milliseconds):
                self.time += simulated_milliseconds

            def snapshot(self):
                status = "completed" if self.time >= 900 else "requested"
                movement = busy_intersection_network().movements[0]
                vehicles = [] if self.time < 500 else [{"trip_id": "trip-1", "movement_id": movement.id, "lane_segment_id": movement.lane_segments[1 if status == "completed" else 0], "position_m": 100 if status == "completed" else 10, "speed_mps": 0}]
                return {"time_ms": self.time, "vehicles": vehicles, "trips": [{"trip_id": "trip-1", "status": status}]}

            def drain_events(self):
                if self.time == 1000 and not self.emitted:
                    self.emitted = True
                    return [{"sequence": 1, "time_ms": 100, "type": "trip.admitted", "entity_id": "trip-1"}, {"sequence": 2, "time_ms": 100, "type": "vehicle.entered", "entity_id": "trip-1"}, {"sequence": 3, "time_ms": 900, "type": "vehicle.exited", "entity_id": "trip-1"}, {"sequence": 4, "time_ms": 900, "type": "trip.completed", "entity_id": "trip-1"}]
                return []

        fake = FakeTransport()
        result = evaluate_transport(fake, scenario, busy_intersection_network(), step_ms=500)
        self.assertIsNotNone(fake.loaded)
        self.assertEqual(result.scenario_id, "fixture")
        self.assertGreater(result.metrics["snapshot_count"], 1)

    def test_transport_residual_drain_is_preserved_and_fails(self) -> None:
        scenario = small_scenario()
        movement = busy_intersection_network().movements[0]

        class SplitTransport:
            def __init__(self) -> None:
                self.time = 0
                self.pending = []

            def load_scenario(self, payload):
                return None

            def reset(self, seed):
                return None

            def advance(self, milliseconds):
                self.time += milliseconds
                if self.time == 500:
                    self.pending = [[{"sequence": 1, "time_ms": 100, "type": "collision", "entity_id": "trip-1"}], [{"sequence": 2, "time_ms": 100, "type": "trip.admitted", "entity_id": "trip-1"}]]

            def snapshot(self):
                return {"time_ms": self.time, "vehicles": [{"trip_id": "trip-1", "movement_id": movement.id, "lane_segment_id": movement.lane_segments[0], "position_m": 5, "speed_mps": 0}], "trips": [{"trip_id": "trip-1", "status": "requested"}]}

            def drain_events(self):
                if self.pending:
                    return self.pending.pop(0)
                return []

        result = evaluate_transport(SplitTransport(), scenario, busy_intersection_network(), step_ms=500)
        self.assertIn("no-safety-events", {item.assertion_id for item in result.assertions if item.result == "fail"})


if __name__ == "__main__":
    unittest.main()
