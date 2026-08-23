from __future__ import annotations

import json
import unittest

from ralph_bench.events import EventRecorder, EventValidationError


class FakeClock:
    def __init__(self, *values: int) -> None:
        self._values = iter(values)

    def __call__(self) -> int:
        return next(self._values)


class EventRecorderTests(unittest.TestCase):
    def test_records_canonical_sequence_and_monotonic_elapsed_time(self) -> None:
        recorder = EventRecorder(FakeClock(1_000_000, 2_000_000, 4_500_000))

        recorder.record(
            phase="agent",
            event_type="model_invocation.started",
            source="conductor",
            attempt=1,
            payload={"evidence_ref": "events/raw/codex.jsonl#spawn"},
        )
        recorder.record(
            phase="agent",
            event_type="attempt.completed",
            source="conductor",
            attempt=1,
        )

        decoded = [json.loads(line) for line in recorder.to_jsonl().splitlines()]
        self.assertEqual([item["sequence"] for item in decoded], [1, 2])
        self.assertEqual([item["time_monotonic_ms"] for item in decoded], [1, 3])
        self.assertEqual(decoded[0]["schema_version"], "event/v1")
        self.assertEqual(decoded[0]["type"], "model_invocation.started")

    def test_payload_is_detached_from_mutable_input(self) -> None:
        clock = FakeClock(0, 1)
        recorder = EventRecorder(clock)
        source = {"nested": {"answer": 1}}
        event = recorder.record(
            phase="preflight", event_type="probe.completed", source="harness", payload=source
        )
        source["nested"]["answer"] = 2
        self.assertEqual(event.to_dict()["payload"]["nested"]["answer"], 1)

    def test_rejects_non_json_and_non_finite_payloads(self) -> None:
        recorder = EventRecorder(FakeClock(0, 1, 2))
        with self.assertRaises(EventValidationError):
            recorder.record(
                phase="agent", event_type="bad", source="fixture", payload={"x": object()}
            )
        with self.assertRaises(EventValidationError):
            recorder.record(
                phase="agent", event_type="bad", source="fixture", payload={"x": float("nan")}
            )

    def test_clock_regression_is_rejected(self) -> None:
        recorder = EventRecorder(FakeClock(10, 9))
        with self.assertRaises(EventValidationError):
            recorder.record(phase="agent", event_type="bad", source="fixture")


if __name__ == "__main__":
    unittest.main()
