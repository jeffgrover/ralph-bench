from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ralph_bench.costs import CostEvidence
from ralph_bench.events import EventRecorder
from ralph_bench.execution import (
    AttemptStore,
    ControlledAttemptLoop,
    HarnessAttemptResult,
    PublicCheckResult,
)


class IncrementingClock:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> int:
        self.value += 1_000_000
        return self.value


class ContractIntegrationTests(unittest.TestCase):
    def test_controlled_loop_preserves_attempts_without_inventing_subscription_cost(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate"
            candidate.mkdir()

            def execute(attempt_number, _feedback, admission):
                (candidate / "index.html").write_text(
                    f"attempt {attempt_number}", encoding="utf-8"
                )
                admission.admit(
                    process_spawned=True,
                    prompt_provided=True,
                    evidence_ref=(
                        f"events/canonical.jsonl#attempt-{attempt_number}"
                    ),
                )
                return HarnessAttemptResult(candidate, "process_exited")

            def check(preserved):
                passed = (
                    preserved / "index.html"
                ).read_text(encoding="utf-8") == "attempt 2"
                return PublicCheckResult(
                    passed,
                    {} if passed else {
                        "failed_assertions": ["traffic-ui-ready"]
                    },
                    ("traffic-ui-ready",),
                )

            recorder = EventRecorder(IncrementingClock())
            loop = ControlledAttemptLoop(
                executor=execute,
                public_checker=check,
                attempt_store=AttemptStore(root / "attempts"),
                recorder=recorder,
            ).run()

            cost = CostEvidence.subscription_unmetered(
                requested_model="gpt-5.6-luna",
                evidence_references=("provenance/sut-resolution.json",),
            )

            self.assertTrue(loop.accepted)
            self.assertEqual(loop.chargeable_attempt_units, 2)
            self.assertEqual(cost.status, "unavailable")
            self.assertIsNone(cost.actual_cost_usd)
            self.assertIsNone(cost.reference_cost_usd)
            self.assertEqual(
                sum(
                    event.event_type == "model_invocation.started"
                    for event in recorder.snapshot()
                ),
                2,
            )


if __name__ == "__main__":
    unittest.main()
