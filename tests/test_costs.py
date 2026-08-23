import dataclasses
import unittest
from decimal import Decimal

from ralph_bench.costs import (
    CHARGE_BASIS,
    POLICY,
    ChargeableAttemptReference,
    CostValidationError,
    ExpectedRunMembership,
    FlatSubscriptionPoolDeclaration,
    RunCostEvidence,
    close_pool,
    close_pool_strict,
    cost_to_green,
)


def declaration(amount="20.00", period="20.00", fraction="1", **overrides):
    values = dict(
        pool_id="pool-1", pool_scope="experiment", currency="USD",
        service_plan="chatgpt-plus", billing_period_cost_usd=period,
        benchmark_allocation_fraction=fraction, pool_cost_usd=amount,
        pool_cost_source="operator_attested_period_charge",
        allocation_rationale="dedicated benchmark period",
        billing_period_start="2026-08-01", billing_period_end="2026-08-31",
    )
    values.update(overrides)
    return FlatSubscriptionPoolDeclaration(**values)


def run(run_id, expected, attempts=1, green=None, pool_declaration=None, **kwargs):
    pool_declaration = pool_declaration or declaration()
    refs = tuple(ChargeableAttemptReference(f"{run_id}-a{i}", f"event-{run_id}-{i}") for i in range(attempts))
    return RunCostEvidence(
        run_id=run_id, pool_id="pool-1", expected_run_ids=tuple(expected.run_ids),
        membership_digest=expected.digest, declaration_digest=pool_declaration.declaration_digest,
        chargeable_attempts=refs,
        generation_started=attempts > 0, green=green, **kwargs,
    )


class CostTests(unittest.TestCase):
    def test_declaration_derives_amount_with_explicit_rounding(self):
        item = declaration(amount="2.01", period="10.03", fraction="0.2")
        self.assertEqual(item.pool_cost_usd, Decimal("2.01"))
        self.assertEqual(item.as_dict()["pool_cost_usd"], "2.01")
        self.assertEqual(item.policy, POLICY)

    def test_amount_mismatch_currency_and_zero_provenance_rejected(self):
        with self.assertRaises(CostValidationError):
            declaration(amount="2.00", period="10.03", fraction="0.2")
        with self.assertRaises(CostValidationError):
            FlatSubscriptionPoolDeclaration(**{**declaration(amount="0.00", period="0.00", fraction="0").as_dict(), "currency": "EUR"})
        with self.assertRaises(CostValidationError):
            declaration(amount="0.00", period="0.00", fraction="0")
        with self.assertRaises(CostValidationError):
            declaration(amount="0.00", period="0.00", fraction="0",).as_dict()

    def test_zero_cost_requires_explicit_evidence_even_for_misleading_source(self):
        with self.assertRaises(CostValidationError):
            FlatSubscriptionPoolDeclaration(
                pool_id="pool-1", pool_scope="experiment", currency="USD",
                service_plan="free-looking", billing_period_cost_usd="0",
                benchmark_allocation_fraction="1", pool_cost_usd="0",
                pool_cost_source="not_free", allocation_rationale="fixture",
                billing_period_start="2026-08-01", billing_period_end="2026-08-31",
            )
        item = FlatSubscriptionPoolDeclaration(
            pool_id="pool-1", pool_scope="experiment", currency="USD",
            service_plan="free-looking", billing_period_cost_usd="0",
            benchmark_allocation_fraction="1", pool_cost_usd="0",
            pool_cost_source="not_free", allocation_rationale="fixture",
            billing_period_start="2026-08-01", billing_period_end="2026-08-31",
            zero_cost_evidence="operator-attested-free-plan#1",
        )
        self.assertEqual(len(item.declaration_digest), 64)

    def test_membership_is_sorted_and_digest_is_order_independent(self):
        a = ExpectedRunMembership.from_ids(["r2", "r1"])
        b = ExpectedRunMembership.from_ids(["r1", "r2"])
        self.assertEqual(a.run_ids, ("r1", "r2"))
        self.assertEqual(a.digest, b.digest)
        with self.assertRaises(CostValidationError):
            ExpectedRunMembership.from_ids(["r1", "r1"])

    def test_green_first_attempt_and_failed_repair_are_allocated(self):
        expected = ExpectedRunMembership.from_ids(["r1", "r2"])
        result = close_pool(declaration(), [run("r1", expected, 1, True), run("r2", expected, 2, False)], expected)
        self.assertTrue(result.closed)
        self.assertEqual([record.primary_cost_usd for record in result.records], [Decimal("6.67"), Decimal("13.33")])
        self.assertEqual(result.pool.total_allocated_usd, Decimal("20.00"))
        self.assertEqual(cost_to_green(result.records), Decimal("20.00"))

    def test_repair_and_failure_cost_to_green_counts_all_generated_runs(self):
        expected = ExpectedRunMembership.from_ids(["r1", "r2", "r3"])
        pool = close_pool_strict(declaration(), [run("r1", expected, 2, True), run("r2", expected, 1, False), run("r3", expected, 1, True)], expected)
        # Total cohort cost / two accepted green runs, including failed r2.
        self.assertEqual(pool.cost_to_green_usd, Decimal("10.00"))

    def test_pre_invocation_zero_weight_is_valid_and_no_green_is_none(self):
        expected = ExpectedRunMembership.from_ids(["r1", "r2"])
        result = close_pool(declaration(), [run("r1", expected, 0, False), run("r2", expected, 1, False)], expected)
        self.assertTrue(result.closed)
        self.assertEqual([x.primary_cost_usd for x in result.records], [Decimal("0.00"), Decimal("20.00")])
        self.assertIsNone(cost_to_green(result.records))

    def test_rounding_uses_largest_remainder_and_tie_breaks_by_run_id(self):
        expected = ExpectedRunMembership.from_ids(["b", "a", "c"])
        pool_declaration = declaration(amount="1.00", period="1.00")
        result = close_pool(pool_declaration, [run("b", expected, 1, pool_declaration=pool_declaration), run("a", expected, 1, pool_declaration=pool_declaration), run("c", expected, 1, pool_declaration=pool_declaration)], expected)
        self.assertTrue(result.closed)
        amounts = {x.run_id: x.primary_cost_usd for x in result.records}
        self.assertEqual(amounts, {"a": Decimal("0.34"), "b": Decimal("0.33"), "c": Decimal("0.33")})

    def test_closure_detects_missing_duplicate_unexpected_and_conflicts(self):
        expected = ExpectedRunMembership.from_ids(["a", "b"])
        base = run("a", expected, 1)
        duplicate = run("a", expected, 1)
        unexpected = run("x", ExpectedRunMembership.from_ids(["a", "b", "x"]), 1)
        result = close_pool(declaration(), [base, duplicate, unexpected], expected)
        self.assertFalse(result.closed)
        self.assertTrue(any("duplicate" in error for error in result.errors))
        self.assertTrue(any("missing" in error for error in result.errors))
        self.assertTrue(any("unexpected" in error for error in result.errors))
        with self.assertRaises(Exception):
            close_pool_strict(declaration(), [base], expected)

    def test_closure_rejects_digest_and_charge_contradictions(self):
        expected = ExpectedRunMembership.from_ids(["a"])
        bad = run("a", expected, 1)
        object.__setattr__(bad, "membership_digest", "bad")
        result = close_pool(declaration(), [bad], expected)
        self.assertFalse(result.closed)
        incomplete = run("a", expected, 1, status="incomplete")
        result = close_pool(declaration(), [incomplete], expected)
        self.assertFalse(result.closed)

    def test_nonconservative_attempt_basis_is_rejected(self):
        with self.assertRaises(CostValidationError):
            ChargeableAttemptReference("a1", "started", "provider_reported")

    def test_immutability_and_interchange_round_trip(self):
        expected = ExpectedRunMembership.from_ids(["a"])
        evidence = run("a", expected, 1, True)
        rebuilt = RunCostEvidence.from_dict(evidence.as_dict())
        self.assertEqual(rebuilt, evidence)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            evidence.run_id = "changed"
        self.assertEqual(evidence.chargeable_attempts[0].charge_basis, CHARGE_BASIS)

    def test_declaration_digest_round_trip_and_pool_conflict(self):
        expected = ExpectedRunMembership.from_ids(["a"])
        evidence = run("a", expected, 1)
        self.assertEqual(RunCostEvidence.from_dict(evidence.as_dict()).declaration_digest,
                         declaration().declaration_digest)
        other = declaration(pool_id="pool-1", period="21.00", amount="21.00")
        conflicting = RunCostEvidence(
            run_id="a", pool_id="pool-1", expected_run_ids=expected.run_ids,
            membership_digest=expected.digest, declaration_digest=other.declaration_digest,
            chargeable_attempts=evidence.chargeable_attempts, generation_started=True,
        )
        result = close_pool(declaration(), [conflicting], expected)
        self.assertFalse(result.closed)
        self.assertTrue(any("declaration digest" in error for error in result.errors))

    def test_deterministic_build_order(self):
        expected = ExpectedRunMembership.from_ids(["a", "b"])
        first = close_pool_strict(declaration(), [run("b", expected, 1), run("a", expected, 2)], expected)
        second = close_pool_strict(declaration(), [run("a", expected, 2), run("b", expected, 1)], expected)
        self.assertEqual(first.records, second.records)


if __name__ == "__main__":
    unittest.main()
