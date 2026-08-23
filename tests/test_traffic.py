from __future__ import annotations

import unittest

from ralph_bench.traffic import (
    NetworkDescription,
    Scenario,
    TrafficEvent,
    TrafficSnapshot,
    build_balanced_scenario,
    busy_intersection_network,
)


class TrafficSchemaTests(unittest.TestCase):
    def test_busy_network_is_connected_and_round_trips(self) -> None:
        network = busy_intersection_network()
        self.assertEqual(network.api_version, "traffic/v1")
        self.assertEqual(len(network.nodes), 4)
        self.assertEqual(len(network.movements), 12)
        self.assertEqual(
            {movement.turn for movement in network.movements},
            {"left", "straight", "right"},
        )
        self.assertEqual(NetworkDescription.from_dict(network.to_dict()), network)

    def test_balanced_scenario_is_deterministic_and_round_trips(self) -> None:
        first = build_balanced_scenario(29)
        second = build_balanced_scenario(29)
        self.assertEqual(first, second)
        self.assertEqual(Scenario.from_dict(first.to_dict()), first)
        self.assertEqual(first.stages[-1].id, "cooldown")
        self.assertTrue(first.stages[-1].cooldown)
        self.assertGreater(len(first.trips), 100)

    def test_browser_payloads_accept_camel_case(self) -> None:
        snapshot = TrafficSnapshot.from_dict(
            {"schemaVersion": "snapshot/v1", "timeMs": 10, "runtimeErrors": []}
        )
        event = TrafficEvent.from_dict(
            {"schemaVersion": "event/v1", "sequence": 1, "timeMs": 10, "type": "signal.changed", "entityId": "movement"}
        )
        self.assertEqual(snapshot.time_ms, 10)
        self.assertEqual(event.event_type, "signal.changed")


if __name__ == "__main__":
    unittest.main()
