from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from ralph_bench.costs import (
    ExpectedRunMembership,
    FlatSubscriptionPoolDeclaration,
    close_pool_strict,
    run_cost_evidence_from_attempts,
)
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
    def test_controlled_loop_invocation_evidence_closes_subscription_pool(self) -> None:
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
                    evidence_ref=f"events/canonical.jsonl#attempt-{attempt_number}",
                )
                return HarnessAttemptResult(candidate, "process_exited")

            def check(preserved):
                passed = (preserved / "index.html").read_text(encoding="utf-8") == "attempt 2"
                return PublicCheckResult(
                    passed,
                    {} if passed else {"failed_assertions": ["traffic-ui-ready"]},
                    ("traffic-ui-ready",),
                )

            recorder = EventRecorder(IncrementingClock())
            loop = ControlledAttemptLoop(
                executor=execute,
                public_checker=check,
                attempt_store=AttemptStore(root / "attempts"),
                recorder=recorder,
            ).run()

            declaration = FlatSubscriptionPoolDeclaration(
                pool_id="p0-a",
                pool_scope="experiment",
                currency="USD",
                service_plan="chatgpt-plus",
                billing_period_cost_usd="20.00",
                benchmark_allocation_fraction="0.25",
                pool_cost_usd="5.00",
                pool_cost_source="operator_attested_period_charge",
                allocation_rationale="quarter of the period allocated to this experiment",
                billing_period_start="2026-08-01",
                billing_period_end="2026-08-31",
            )
            membership = ExpectedRunMembership.from_ids(("run-1",))
            evidence = run_cost_evidence_from_attempts(
                run_id="run-1",
                declaration=declaration,
                membership=membership,
                attempts=loop.attempts,
                green=loop.accepted,
            )

            pool = close_pool_strict(declaration, (evidence,), membership)
            self.assertTrue(loop.accepted)
            self.assertEqual(loop.chargeable_attempt_units, 2)
            self.assertEqual(pool.records[0].chargeable_attempt_units, 2)
            self.assertEqual(pool.records[0].primary_cost_usd, Decimal("5.00"))
            self.assertEqual(pool.cost_to_green_usd, Decimal("5.00"))
            self.assertEqual(
                sum(
                    event.event_type == "model_invocation.started"
                    for event in recorder.snapshot()
                ),
                2,
            )


if __name__ == "__main__":
    unittest.main()
