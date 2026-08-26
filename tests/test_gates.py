from __future__ import annotations

import unittest

from ralph_bench.gates import (
    GATES_PROTOCOL,
    CarArrival,
    GateSchemaError,
    PedestrianArrival,
    balanced_seed_for_repetition,
    build_balanced_gate_scenario,
)


class GateSchemaTests(unittest.TestCase):
    def test_balanced_scenario_is_small_deterministic_and_complete(self) -> None:
        first = build_balanced_gate_scenario(29)
        second = build_balanced_gate_scenario(29)
        self.assertEqual(first, second)
        self.assertEqual(first.to_dict()["protocol"], GATES_PROTOCOL)
        self.assertEqual(first.stages[-1].id, "cooldown")
        self.assertTrue(first.stages[-1].cooldown)
        self.assertGreater(len(first.cars), 40)
        self.assertGreater(len(first.pedestrians), 5)
        self.assertTrue(all(car.enters_from != car.exits_to for car in first.cars))

    def test_arrival_shapes_reject_unknown_gates_and_invalid_crossing_directions(self) -> None:
        with self.assertRaises(GateSchemaError):
            CarArrival("car", "north", "north", 0)
        with self.assertRaises(GateSchemaError):
            PedestrianArrival("ped", "north", "north-to-south", 0)

    def test_seed_repetition_mapping_is_declared(self) -> None:
        self.assertEqual(
            [balanced_seed_for_repetition(item) for item in (1, 2, 3, 4)],
            [17, 29, 43, 17],
        )


if __name__ == "__main__":
    unittest.main()
