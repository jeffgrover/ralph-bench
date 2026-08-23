from __future__ import annotations

from decimal import Decimal
import unittest

from ralph_bench.costs import CostEvidence, CostValidationError


class CostEvidenceTests(unittest.TestCase):
    def test_subscription_unmetered_is_unavailable_not_zero(self) -> None:
        evidence = CostEvidence.subscription_unmetered(
            requested_model="gpt-5.6-luna",
            evidence_references=("provenance/sut-resolution.json",),
        )

        self.assertEqual(evidence.billing_mode, "flat_subscription")
        self.assertEqual(evidence.status, "unavailable")
        self.assertIsNone(evidence.actual_cost_usd)
        self.assertIsNone(evidence.reference_cost_usd)
        self.assertIn("does not expose", evidence.unavailable_reason)
        self.assertEqual(CostEvidence.from_dict(evidence.as_dict()), evidence)

    def test_actual_and_reference_cost_can_coexist(self) -> None:
        evidence = CostEvidence(
            status="complete",
            billing_mode="metered_api",
            actual_cost_usd="0.0005080",
            reference_cost_usd="0.000500",
            actual_source="openrouter_usage_debit",
            reference_source="openrouter_catalog_snapshot",
            requested_model="openai/gpt-5.6-luna",
            canonical_model="openai/gpt-5.6-luna",
            token_basis="openrouter_reported",
            price_snapshot_id="catalog-2026-08-23T12:00:00Z",
            price_snapshot_hash="a" * 64,
            price_snapshot_at="2026-08-23T12:00:00Z",
            generation_id="gen-123",
            route="OpenAI",
            evidence_references=(
                "events/raw/openrouter.jsonl#gen-123",
                "provenance/pricing/openrouter-catalog.json",
            ),
        )

        self.assertEqual(evidence.actual_cost_usd, Decimal("0.0005080"))
        self.assertEqual(evidence.reference_cost_usd, Decimal("0.000500"))
        wire = evidence.as_dict()
        self.assertEqual(wire["actual_cost_usd"], "0.000508")
        self.assertEqual(wire["reference_cost_usd"], "0.0005")
        self.assertEqual(CostEvidence.from_dict(wire), evidence)

    def test_provisional_reference_is_allowed_without_actual_cost(self) -> None:
        evidence = CostEvidence(
            status="provisional",
            billing_mode="flat_subscription",
            reference_cost_usd="0.03",
            reference_source="openrouter_catalog_snapshot",
            token_basis="provider_reported",
            evidence_references=("events/raw/provider.jsonl#usage",),
        )
        self.assertIsNone(evidence.actual_cost_usd)
        self.assertEqual(evidence.reference_cost_usd, Decimal("0.03"))

        with self.assertRaisesRegex(CostValidationError, "provenance"):
            CostEvidence(
                status="complete",
                billing_mode="metered_api",
                reference_cost_usd="0.03",
                reference_source="openrouter_catalog_snapshot",
                evidence_references=("events/raw/provider.jsonl#usage",),
            )

    def test_unavailable_requires_reason_and_forbids_amounts(self) -> None:
        with self.assertRaisesRegex(CostValidationError, "unavailable_reason"):
            CostEvidence(status="unavailable", billing_mode="flat_subscription")
        with self.assertRaisesRegex(CostValidationError, "cannot contain"):
            CostEvidence(
                status="unavailable",
                billing_mode="flat_subscription",
                actual_cost_usd="0",
                actual_source="provider",
                unavailable_reason="not available",
            )

    def test_available_status_requires_amount_and_matching_source(self) -> None:
        with self.assertRaisesRegex(CostValidationError, "at least one"):
            CostEvidence(status="complete", billing_mode="metered_api")
        with self.assertRaisesRegex(CostValidationError, "actual_source"):
            CostEvidence(
                status="complete",
                billing_mode="metered_api",
                actual_cost_usd="0.01",
            )
        with self.assertRaisesRegex(CostValidationError, "reference_source"):
            CostEvidence(
                status="provisional",
                billing_mode="metered_api",
                reference_cost_usd="0.01",
            )

    def test_cost_amounts_are_nonnegative_finite_decimals(self) -> None:
        for bad in ("-0.01", "NaN", "Infinity", True, 0.01):
            with self.subTest(value=bad):
                with self.assertRaises(CostValidationError):
                    CostEvidence(
                        status="complete",
                        billing_mode="metered_api",
                        actual_cost_usd=bad,
                        actual_source="provider",
                    )

    def test_billing_mode_and_currency_are_closed_contracts(self) -> None:
        with self.assertRaisesRegex(CostValidationError, "billing_mode"):
            CostEvidence(
                status="unavailable",
                billing_mode="made_up",
                unavailable_reason="not available",
            )
        with self.assertRaisesRegex(CostValidationError, "currency must be USD"):
            CostEvidence(
                status="unavailable",
                billing_mode="flat_subscription",
                currency="EUR",
                unavailable_reason="not available",
            )

    def test_numeric_cost_requires_evidence_even_when_zero(self) -> None:
        with self.assertRaisesRegex(CostValidationError, "evidence_reference"):
            CostEvidence(
                status="complete",
                billing_mode="metered_api",
                actual_cost_usd="0",
                actual_source="openrouter_usage_debit",
            )

    def test_decimal_precision_and_exponent_are_bounded(self) -> None:
        for bad in ("1e999999999", "1e-999999999", "1000000000000.01"):
            with self.subTest(value=bad):
                with self.assertRaisesRegex(CostValidationError, "precision or range"):
                    CostEvidence(
                        status="complete",
                        billing_mode="metered_api",
                        actual_cost_usd=bad,
                        actual_source="provider",
                        evidence_references=("events/raw/provider.jsonl#usage",),
                    )

    def test_direct_constructor_rejects_non_array_reference_container(self) -> None:
        for bad in ("cost.json#one", None, 42):
            with self.subTest(value=bad):
                with self.assertRaisesRegex(CostValidationError, "array"):
                    CostEvidence(
                        status="unavailable",
                        billing_mode="flat_subscription",
                        unavailable_reason="not available",
                        evidence_references=bad,  # type: ignore[arg-type]
                    )

    def test_unknown_fields_and_bad_references_are_rejected(self) -> None:
        with self.assertRaisesRegex(CostValidationError, "invalid cost evidence"):
            CostEvidence.from_dict(
                {
                    **CostEvidence.subscription_unmetered().as_dict(),
                    "surprise": True,
                }
            )
        with self.assertRaisesRegex(CostValidationError, "unique"):
            CostEvidence.subscription_unmetered(
                evidence_references=("cost.json#one", "cost.json#one")
            )
        malformed = CostEvidence.subscription_unmetered().as_dict()
        malformed["evidence_references"] = "not-an-array"
        with self.assertRaisesRegex(CostValidationError, "array"):
            CostEvidence.from_dict(malformed)


if __name__ == "__main__":
    unittest.main()
