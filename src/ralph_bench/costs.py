"""Typed, run-side cost evidence.

Experiment files describe intent; they never ask an operator to invent a
per-run subscription charge.  A run instead records the cost evidence that
was actually available. P0-A implements honest unavailable cases for ChatGPT
subscription access and local inference. The nullable actual/reference split
is retained because OpenRouter is the next provider slice and may supply both
values.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "cost/v1"
STATUSES = frozenset({"complete", "provisional", "unavailable"})
BILLING_MODES = frozenset(
    {
        "metered_api",
        "flat_subscription",
        "provider_credits",
        "local",
        "other_declared",
    }
)
CURRENCY = "USD"

# Cost totals are deliberately bounded before fixed-point serialization.  The
# limits are generous for a single benchmark run while preventing adversarial
# Decimal exponents from expanding into an enormous JSON string.
_MAX_USD = Decimal("1000000000000")
_MAX_DECIMAL_DIGITS = 30
_MIN_DECIMAL_EXPONENT = -18
_MAX_DECIMAL_EXPONENT = 12


class CostValidationError(ValueError):
    """Cost evidence is malformed or internally inconsistent."""


def _nonempty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CostValidationError(f"{field_name} must be a non-empty string")
    return value


def _optional_nonempty(value: str | None, field_name: str) -> str | None:
    if value is not None:
        _nonempty(value, field_name)
    return value


def _usd(value: Decimal | int | str | None, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (bool, float)):
        raise CostValidationError(
            f"{field_name} must be a decimal string or integer, not "
            f"{type(value).__name__}"
        )
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CostValidationError(f"{field_name} must be a decimal") from exc
    if not result.is_finite():
        raise CostValidationError(f"{field_name} must be finite")
    if result < 0:
        raise CostValidationError(f"{field_name} cannot be negative")
    _, digits, exponent = result.as_tuple()
    if (
        len(digits) > _MAX_DECIMAL_DIGITS
        or exponent < _MIN_DECIMAL_EXPONENT
        or exponent > _MAX_DECIMAL_EXPONENT
        or result > _MAX_USD
    ):
        raise CostValidationError(
            f"{field_name} is outside the supported precision or range"
        )
    return result


def _wire_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _references(values: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise CostValidationError(
            "evidence_references must be an array of strings"
        )
    result = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise CostValidationError(
            "evidence_references must contain non-empty strings"
        )
    if len(set(result)) != len(result):
        raise CostValidationError("evidence_references must be unique")
    return result


@dataclass(frozen=True, slots=True)
class CostEvidence:
    """Versioned cost facts for one run.

    ``actual_cost_usd`` is an attributable charge/debit reported by the route
    used for inference. ``reference_cost_usd`` is a normalized comparison
    derived from a named price source. They are intentionally independent and
    may both be present. ``status`` expresses evidence completeness, not which
    of the two bases is populated.
    """

    status: str
    billing_mode: str
    actual_cost_usd: Decimal | int | str | None = None
    reference_cost_usd: Decimal | int | str | None = None
    actual_source: str | None = None
    reference_source: str | None = None
    unavailable_reason: str | None = None
    currency: str = "USD"
    requested_model: str | None = None
    canonical_model: str | None = None
    token_basis: str | None = None
    price_snapshot_id: str | None = None
    price_snapshot_hash: str | None = None
    price_snapshot_at: str | None = None
    generation_id: str | None = None
    route: str | None = None
    evidence_references: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise CostValidationError(
                f"unsupported schema_version: {self.schema_version!r}"
            )
        if not isinstance(self.status, str) or self.status not in STATUSES:
            raise CostValidationError(
                "status must be complete, provisional, or unavailable"
            )
        if (
            not isinstance(self.billing_mode, str)
            or self.billing_mode not in BILLING_MODES
        ):
            raise CostValidationError(
                "billing_mode must be metered_api, flat_subscription, "
                "provider_credits, local, or other_declared"
            )
        if self.currency != CURRENCY:
            raise CostValidationError("currency must be USD")

        actual = _usd(self.actual_cost_usd, "actual_cost_usd")
        reference = _usd(self.reference_cost_usd, "reference_cost_usd")
        object.__setattr__(self, "actual_cost_usd", actual)
        object.__setattr__(self, "reference_cost_usd", reference)

        optional_strings = (
            "actual_source",
            "reference_source",
            "unavailable_reason",
            "requested_model",
            "canonical_model",
            "token_basis",
            "price_snapshot_id",
            "price_snapshot_hash",
            "price_snapshot_at",
            "generation_id",
            "route",
        )
        for field_name in optional_strings:
            _optional_nonempty(getattr(self, field_name), field_name)

        if actual is None and self.actual_source is not None:
            raise CostValidationError(
                "actual_source requires actual_cost_usd"
            )
        if actual is not None and self.actual_source is None:
            raise CostValidationError(
                "actual_cost_usd requires actual_source"
            )
        if reference is None and self.reference_source is not None:
            raise CostValidationError(
                "reference_source requires reference_cost_usd"
            )
        if reference is not None and self.reference_source is None:
            raise CostValidationError(
                "reference_cost_usd requires reference_source"
            )

        references = _references(self.evidence_references)
        object.__setattr__(self, "evidence_references", references)

        has_amount = actual is not None or reference is not None
        if self.status == "unavailable":
            if has_amount:
                raise CostValidationError(
                    "unavailable cost evidence cannot contain a USD amount"
                )
            if self.unavailable_reason is None:
                raise CostValidationError(
                    "unavailable cost evidence requires unavailable_reason"
                )
        else:
            if not has_amount:
                raise CostValidationError(
                    f"{self.status} cost evidence requires at least one USD amount"
                )
            if not references:
                raise CostValidationError(
                    "numeric cost evidence requires at least one evidence_reference"
                )
            if self.unavailable_reason is not None:
                raise CostValidationError(
                    "available cost evidence cannot contain unavailable_reason"
                )

        if self.status == "complete" and reference is not None:
            required_reference_fields = (
                "requested_model",
                "canonical_model",
                "token_basis",
                "price_snapshot_id",
                "price_snapshot_hash",
                "price_snapshot_at",
            )
            missing = [
                field_name
                for field_name in required_reference_fields
                if getattr(self, field_name) is None
            ]
            if missing:
                raise CostValidationError(
                    "complete reference cost is missing provenance field(s): "
                    + ", ".join(missing)
                )

    @classmethod
    def unavailable_for_billing_mode(
        cls,
        *,
        billing_mode: str,
        requested_model: str | None = None,
        evidence_references: Iterable[str] = (),
    ) -> "CostEvidence":
        """Create unavailable evidence from the resolved provider billing mode."""

        reasons = {
            "flat_subscription": (
                "subscription provider does not expose attributable per-run "
                "USD cost"
            ),
            "local": "local inference has no attributable per-run USD charge",
            "metered_api": "metered provider did not expose attributable per-run USD cost",
            "provider_credits": "provider credits did not expose attributable per-run USD cost",
            "other_declared": "provider did not expose attributable per-run USD cost",
        }

        return cls(
            status="unavailable",
            billing_mode=billing_mode,
            unavailable_reason=reasons.get(
                billing_mode, "provider did not expose attributable per-run USD cost"
            ),
            requested_model=requested_model,
            evidence_references=tuple(evidence_references),
        )

    @classmethod
    def subscription_unmetered(
        cls,
        *,
        requested_model: str | None = None,
        evidence_references: Iterable[str] = (),
    ) -> "CostEvidence":
        """Create the P0-A ChatGPT subscription result."""

        return cls.unavailable_for_billing_mode(
            billing_mode="flat_subscription",
            requested_model=requested_model,
            evidence_references=evidence_references,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "billing_mode": self.billing_mode,
            "currency": self.currency,
            "actual_cost_usd": _wire_decimal(self.actual_cost_usd),
            "reference_cost_usd": _wire_decimal(self.reference_cost_usd),
            "actual_source": self.actual_source,
            "reference_source": self.reference_source,
            "unavailable_reason": self.unavailable_reason,
            "requested_model": self.requested_model,
            "canonical_model": self.canonical_model,
            "token_basis": self.token_basis,
            "price_snapshot_id": self.price_snapshot_id,
            "price_snapshot_hash": self.price_snapshot_hash,
            "price_snapshot_at": self.price_snapshot_at,
            "generation_id": self.generation_id,
            "route": self.route,
            "evidence_references": list(self.evidence_references),
        }

    to_dict = as_dict

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CostEvidence":
        values = dict(data)
        raw_references = values.get("evidence_references", ())
        if not isinstance(raw_references, (list, tuple)):
            raise CostValidationError(
                "evidence_references must be an array of strings"
            )
        values["evidence_references"] = tuple(raw_references)
        try:
            return cls(**values)
        except TypeError as exc:
            raise CostValidationError(f"invalid cost evidence fields: {exc}") from exc


__all__ = [
    "BILLING_MODES",
    "CURRENCY",
    "SCHEMA_VERSION",
    "STATUSES",
    "CostEvidence",
    "CostValidationError",
]
