from __future__ import annotations

import math
import unittest

from ralph_bench.collision_observer import analyze_observations


def monitor(*samples: dict[str, object]) -> dict[str, object]:
    return {
        "issued": [
            {"id": "car-a", "kind": "car"},
            {"id": "car-b", "kind": "car"},
        ],
        "observations": list(samples),
        "invalid_observations": [],
    }


def body(identifier: str, x: float, y: float, heading: float = 0.0) -> dict[str, object]:
    return {
        "id": identifier,
        "x": x,
        "y": y,
        "length": 4.0,
        "width": 1.8,
        "heading": heading,
    }


class CollisionObserverTests(unittest.TestCase):
    def test_reports_contact_between_oriented_footprints(self) -> None:
        result = analyze_observations(
            monitor(
                {"time_ms": 0, "bodies": [body("car-a", 0, 0), body("car-b", 2, 0)]},
                {"time_ms": 100, "bodies": [body("car-a", 0, 0), body("car-b", 2, 0)]},
            )
        )
        self.assertEqual(len(result["collisions"]), 1)
        self.assertEqual(result["collisions"][0]["ids"], ["car-a", "car-b"])

    def test_swept_check_catches_crossing_between_samples(self) -> None:
        result = analyze_observations(
            monitor(
                {"time_ms": 0, "bodies": [body("car-a", -5, 0), body("car-b", 0, -5, math.pi / 2)]},
                {"time_ms": 100, "bodies": [body("car-a", 5, 0), body("car-b", 0, 5, math.pi / 2)]},
            )
        )
        self.assertEqual(len(result["collisions"]), 1)

    def test_stationary_close_queue_is_not_a_collision(self) -> None:
        result = analyze_observations(
            monitor(
                {"time_ms": 0, "bodies": [body("car-a", 0, 0), body("car-b", 5, 0)]},
                {"time_ms": 100, "bodies": [body("car-a", 0, 0), body("car-b", 5, 0)]},
            )
        )
        self.assertEqual(result["collisions"], [])
        self.assertEqual(result["collision_score"], 1)

    def test_high_speed_following_is_not_a_collision(self) -> None:
        result = analyze_observations(
            monitor(
                {"time_ms": 0, "bodies": [body("car-a", 0, 0), body("car-b", 7, 0)]},
                {"time_ms": 100, "bodies": [body("car-a", 3, 0), body("car-b", 10, 0)]},
            )
        )
        self.assertEqual(result["collisions"], [])
        self.assertEqual(result["collision_score"], 1)

    def test_missing_or_sparse_trace_is_explicitly_incomplete(self) -> None:
        result = analyze_observations(
            monitor(
                {"time_ms": 0, "bodies": [body("car-a", 0, 0)]},
                {"time_ms": 250, "bodies": [body("car-a", 1, 0)]},
            )
        )
        self.assertFalse(result["coverage_complete"])
        self.assertEqual(result["missing_ids"], ["car-b"])
        self.assertEqual(result["max_gap_ms"], 250)


if __name__ == "__main__":
    unittest.main()
