"""Pure, deterministic cost-domain types for Ralph Bench.

P0's subscription policy is deliberately small: an experiment declares one
USD pool and each conductor-admitted model invocation contributes one unit.
This module contains no filesystem, provider, or reporting concerns.  Values
crossing the interchange boundary are decimal strings; calculations use
``Decimal`` and integer cents, never binary floating point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence

POLICY = "flat-subscription-attempt-pool/v1"
USD = "USD"
CLOSURE_RULE = "all_expected_runs_terminal"
CHARGE_BASIS = "conservative_invocation_started"
_CENT = Decimal("0.01")
_ZERO = Decimal("0")


class CostError(ValueError):
    """Base error for malformed or semantically inconsistent cost evidence."""


class CostValidationError(CostError):
    pass


class PoolClosureError(CostError):
    """Raised by the strict close helper when a pool cannot be closed."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(errors)
        super().__init__("cost pool is incomplete: " + "; ".join(self.errors))


def _decimal(value: Decimal | int | str, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise CostValidationError(f"{field_name} must be a decimal, not bool")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise CostValidationError(f"{field_name} must be a decimal") from exc
    if not result.is_finite():
        raise CostValidationError(f"{field_name} must be finite")
    return result


def _money(value: Decimal | int | str, field_name: str) -> Decimal:
    result = _decimal(value, field_name)
    if result < 0:
        raise CostValidationError(f"{field_name} cannot be negative")
    return result.quantize(_CENT, rounding=ROUND_HALF_UP)


def _nonempty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CostValidationError(f"{field_name} must be a non-empty string")
    return value


def _tuple_strings(values: Iterable[str], field_name: str) -> tuple[str, ...]:
    result = tuple(values)
    if any(not isinstance(value, str) or not value for value in result):
        raise CostValidationError(f"{field_name} must contain non-empty strings")
    return result


def _iso_date(value: str, field_name: str) -> str:
    _nonempty(value, field_name)
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CostValidationError(f"{field_name} must be an ISO date") from exc
    return value


def _wire_decimal(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else format(value, "f")


def _canonical_decimal(value: Decimal) -> str:
    """Stable non-exponential decimal spelling for mechanical keys."""
    normalized = value.normalize()
    return format(normalized, "f")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_membership_digest(run_ids: Iterable[str]) -> str:
    """Return the SHA-256 digest of the canonical sorted expected-ID list.

    Duplicate IDs are rejected instead of silently deduplicated.  This is
    important because duplicate members must remain a closure error.
    """
    ids = _tuple_strings(run_ids, "run_ids")
    if len(set(ids)) != len(ids):
        raise CostValidationError("expected run IDs must be unique")
    return _digest(sorted(ids))


@dataclass(frozen=True)
class ExpectedRunMembership:
    run_ids: tuple[str, ...]
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        ids = _tuple_strings(self.run_ids, "run_ids")
        if len(set(ids)) != len(ids):
            raise CostValidationError("expected run IDs must be unique")
        object.__setattr__(self, "run_ids", tuple(sorted(ids)))
        object.__setattr__(self, "digest", canonical_membership_digest(ids))

    @classmethod
    def from_ids(cls, run_ids: Iterable[str]) -> "ExpectedRunMembership":
        return cls(tuple(run_ids))

    @property
    def membership_digest(self) -> str:
        return self.digest

    def as_dict(self) -> dict[str, Any]:
        return {"expected_run_ids": list(self.run_ids), "membership_digest": self.digest}


@dataclass(frozen=True)
class ComparabilityKey:
    """Mechanical cohort identity; keys are never inferred from labels."""

    billing_mode: str
    policy: str
    currency: str
    pool_scope: str
    pool_cost_source: str
    allocation_basis: str
    allocation_fraction: str
    charge_scope: str

    def as_tuple(self) -> tuple[str, ...]:
        return (self.billing_mode, self.policy, self.currency, self.pool_scope,
                self.pool_cost_source, self.allocation_basis,
                self.allocation_fraction, self.charge_scope)

    def as_string(self) -> str:
        return "|".join(self.as_tuple())


@dataclass(frozen=True)
class FlatSubscriptionPoolDeclaration:
    """Validated experiment-scoped declaration for the P0 flat plan pool."""

    pool_id: str
    pool_scope: str
    currency: str
    service_plan: str
    billing_period_cost_usd: Decimal | str
    benchmark_allocation_fraction: Decimal | str
    pool_cost_usd: Decimal | str
    pool_cost_source: str
    allocation_rationale: str
    billing_period_start: str
    billing_period_end: str
    policy: str = POLICY
    closure: str = CLOSURE_RULE
    rounding: str = "USD-0.01-half-up"
    charge_scope: str = "model_invocation"
    zero_cost_evidence: Optional[str] = None

    def __post_init__(self) -> None:
        _nonempty(self.pool_id, "pool_id")
        if self.pool_scope != "experiment":
            raise CostValidationError("P0 subscription pools must have pool_scope='experiment'")
        if self.policy != POLICY:
            raise CostValidationError(f"unsupported cost policy: {self.policy}")
        if self.currency != USD:
            raise CostValidationError("flat subscription allocation is USD-only")
        if self.closure != CLOSURE_RULE:
            raise CostValidationError(f"unsupported closure rule: {self.closure}")
        if self.rounding != "USD-0.01-half-up":
            raise CostValidationError("rounding must be explicit USD-0.01-half-up")
        _nonempty(self.service_plan, "service_plan")
        _nonempty(self.pool_cost_source, "pool_cost_source")
        _nonempty(self.allocation_rationale, "allocation_rationale")
        _nonempty(self.charge_scope, "charge_scope")
        start = _iso_date(self.billing_period_start, "billing_period_start")
        end = _iso_date(self.billing_period_end, "billing_period_end")
        if date.fromisoformat(start) > date.fromisoformat(end):
            raise CostValidationError("billing period ends before it starts")
        period = _decimal(self.billing_period_cost_usd, "billing_period_cost_usd")
        if period < 0:
            raise CostValidationError("billing_period_cost_usd cannot be negative")
        fraction = _decimal(self.benchmark_allocation_fraction, "benchmark_allocation_fraction")
        amount = _money(self.pool_cost_usd, "pool_cost_usd")
        if fraction < 0 or fraction > 1:
            raise CostValidationError("benchmark_allocation_fraction must be between 0 and 1")
        if self.zero_cost_evidence is not None:
            _nonempty(self.zero_cost_evidence, "zero_cost_evidence")
        expected = (period * fraction).quantize(_CENT, rounding=ROUND_HALF_UP)
        if amount != expected:
            raise CostValidationError("pool_cost_usd must equal rounded period charge × allocation fraction")
        if amount == _ZERO and not self.zero_cost_evidence:
            raise CostValidationError("zero pool cost requires explicit evidence of a genuinely free/zero-price plan")
        object.__setattr__(self, "billing_period_cost_usd", period)
        object.__setattr__(self, "benchmark_allocation_fraction", fraction)
        object.__setattr__(self, "pool_cost_usd", amount)

    @property
    def billing_mode(self) -> str:
        return "flat_subscription"

    @property
    def allocation_basis(self) -> str:
        return "chargeable_attempt_units"

    @property
    def comparability_key(self) -> ComparabilityKey:
        return ComparabilityKey(
            self.billing_mode, self.policy, self.currency, self.pool_scope,
            self.pool_cost_source, self.allocation_basis,
            _canonical_decimal(self.benchmark_allocation_fraction), self.charge_scope,
        )

    @property
    def declaration_digest(self) -> str:
        """Canonical digest of every declaration field, including policy/version."""
        return canonical_declaration_digest(self)

    # Explicit helper spelling for callers that do not retain the declaration
    # as an object at the bundle boundary.
    def digest(self) -> str:
        return self.declaration_digest

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy, "pool_id": self.pool_id, "pool_scope": self.pool_scope,
            "currency": self.currency, "service_plan": self.service_plan,
            "billing_period_cost_usd": _wire_decimal(self.billing_period_cost_usd),
            "benchmark_allocation_fraction": _wire_decimal(self.benchmark_allocation_fraction),
            "pool_cost_usd": _wire_decimal(self.pool_cost_usd),
            "pool_cost_source": self.pool_cost_source, "allocation_rationale": self.allocation_rationale,
            "billing_period_start": self.billing_period_start, "billing_period_end": self.billing_period_end,
            "closure": self.closure, "rounding": self.rounding, "charge_scope": self.charge_scope,
            "zero_cost_evidence": self.zero_cost_evidence,
        }

    to_dict = as_dict

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FlatSubscriptionPoolDeclaration":
        return cls(**dict(data))


def canonical_declaration_digest(declaration: "FlatSubscriptionPoolDeclaration") -> str:
    """Return the stable SHA-256 digest used on every run cost evidence record."""
    return _digest(declaration.as_dict())


@dataclass(frozen=True)
class ChargeableAttemptReference:
    attempt_id: str
    generation_started_evidence: str
    charge_basis: str = CHARGE_BASIS

    def __post_init__(self) -> None:
        _nonempty(self.attempt_id, "attempt_id")
        _nonempty(self.generation_started_evidence, "generation_started_evidence")
        if self.charge_basis != CHARGE_BASIS:
            raise CostValidationError("P0 attempts require conservative invocation-started charge basis")

    def as_dict(self) -> dict[str, str]:
        return {"attempt_id": self.attempt_id,
                "generation_started_evidence": self.generation_started_evidence,
                "charge_basis": self.charge_basis}


@dataclass(frozen=True)
class RunCostEvidence:
    """Immutable bundle-side cost evidence for one run."""

    run_id: str
    pool_id: str
    expected_run_ids: tuple[str, ...]
    membership_digest: str
    declaration_digest: str
    chargeable_attempts: tuple[ChargeableAttemptReference, ...] = ()
    currency: str = USD
    status: str = "complete"
    terminal: bool = True
    generation_started: Optional[bool] = None
    green: Optional[bool] = None
    evidence_references: tuple[str, ...] = ()
    # Nullable secondary vector fields remain separate from allocated cost.
    provider_billed_usd: Optional[Decimal | str] = None
    marginal_cash_usd: Optional[Decimal | str] = None
    list_price_equivalent_usd: Optional[Decimal | str] = None
    provider_credits_reported: Optional[str] = None
    credit_equivalent: Optional[str] = None

    def __post_init__(self) -> None:
        _nonempty(self.run_id, "run_id")
        _nonempty(self.pool_id, "pool_id")
        if self.currency != USD:
            raise CostValidationError("P0 cost evidence must be USD")
        if self.status not in {"complete", "provisional", "incomplete"}:
            raise CostValidationError("invalid cost evidence status")
        ids = _tuple_strings(self.expected_run_ids, "expected_run_ids")
        if len(set(ids)) != len(ids):
            raise CostValidationError("expected run IDs must be unique")
        if self.membership_digest != canonical_membership_digest(ids):
            raise CostValidationError("membership digest does not match expected run IDs")
        if not isinstance(self.declaration_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", self.declaration_digest):
            raise CostValidationError("declaration_digest must be a canonical SHA-256 hex digest")
        attempts = tuple(self.chargeable_attempts)
        if any(not isinstance(item, ChargeableAttemptReference) for item in attempts):
            raise CostValidationError("chargeable_attempts must contain attempt references")
        if len({item.attempt_id for item in attempts}) != len(attempts):
            raise CostValidationError("duplicate chargeable attempt reference")
        started = bool(attempts) if self.generation_started is None else self.generation_started
        if not isinstance(started, bool):
            raise CostValidationError("generation_started must be bool or null")
        if not started and attempts:
            raise CostValidationError("pre-invocation evidence cannot contain chargeable attempts")
        if started and not attempts:
            raise CostValidationError("invocation-started evidence requires a chargeable attempt reference")
        if not self.terminal:
            # Open evidence can be retained but is never eligible for closure.
            if self.status == "complete":
                object.__setattr__(self, "status", "provisional")
        refs = _tuple_strings(self.evidence_references, "evidence_references")
        object.__setattr__(self, "expected_run_ids", tuple(sorted(ids)))
        object.__setattr__(self, "chargeable_attempts", attempts)
        object.__setattr__(self, "generation_started", started)
        object.__setattr__(self, "evidence_references", refs)
        for name in ("provider_billed_usd", "marginal_cash_usd", "list_price_equivalent_usd"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _money(value, name))

    @property
    def attempt_count(self) -> int:
        return len(self.chargeable_attempts)

    @property
    def chargeable_attempt_references(self) -> tuple[ChargeableAttemptReference, ...]:
        return self.chargeable_attempts

    @property
    def pre_invocation(self) -> bool:
        return not self.generation_started

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "pool_id": self.pool_id,
            "expected_run_ids": list(self.expected_run_ids),
            "membership_digest": self.membership_digest,
            "declaration_digest": self.declaration_digest,
            "currency": self.currency, "status": self.status, "terminal": self.terminal,
            "generation_started": self.generation_started, "green": self.green,
            "chargeable_attempts": [item.as_dict() for item in self.chargeable_attempts],
            "evidence_references": list(self.evidence_references),
            "provider_billed_usd": _wire_decimal(self.provider_billed_usd),
            "marginal_cash_usd": _wire_decimal(self.marginal_cash_usd),
            "list_price_equivalent_usd": _wire_decimal(self.list_price_equivalent_usd),
            "provider_credits_reported": self.provider_credits_reported,
            "credit_equivalent": self.credit_equivalent,
        }

    to_dict = as_dict

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunCostEvidence":
        values = dict(data)
        values["chargeable_attempts"] = tuple(ChargeableAttemptReference(**item) for item in values.get("chargeable_attempts", ()))
        values["expected_run_ids"] = tuple(values.get("expected_run_ids", ()))
        values["evidence_references"] = tuple(values.get("evidence_references", ()))
        return cls(**values)


class InvocationAttemptObservation(Protocol):
    """Structural boundary implemented by conductor attempt records."""

    attempt_number: int
    invocation_started: bool
    invocation_evidence_ref: str | None


def run_cost_evidence_from_attempts(
    *,
    run_id: str,
    declaration: FlatSubscriptionPoolDeclaration,
    membership: ExpectedRunMembership,
    attempts: Iterable[InvocationAttemptObservation],
    green: Optional[bool],
    status: str = "complete",
    terminal: bool = True,
) -> RunCostEvidence:
    """Convert conductor-owned admission evidence into immutable cost evidence."""

    observations = tuple(attempts)
    attempt_numbers = [item.attempt_number for item in observations]
    if any(number < 1 for number in attempt_numbers):
        raise CostValidationError("attempt numbers must be positive")
    if len(set(attempt_numbers)) != len(attempt_numbers):
        raise CostValidationError("attempt numbers must be unique")
    references: list[ChargeableAttemptReference] = []
    for item in observations:
        if item.invocation_started:
            if item.invocation_evidence_ref is None:
                raise CostValidationError(
                    "an admitted invocation is missing its evidence reference"
                )
            references.append(
                ChargeableAttemptReference(
                    attempt_id=f"{run_id}-attempt-{item.attempt_number}",
                    generation_started_evidence=item.invocation_evidence_ref,
                )
            )
        elif item.invocation_evidence_ref is not None:
            raise CostValidationError(
                "a pre-invocation attempt cannot carry invocation-start evidence"
            )
    chargeable_attempts = tuple(references)
    return RunCostEvidence(
        run_id=run_id,
        pool_id=declaration.pool_id,
        expected_run_ids=membership.run_ids,
        membership_digest=membership.digest,
        declaration_digest=declaration.declaration_digest,
        chargeable_attempts=chargeable_attempts,
        generation_started=bool(chargeable_attempts),
        green=green,
        status=status,
        terminal=terminal,
        evidence_references=tuple(
            item.generation_started_evidence for item in chargeable_attempts
        ),
    )


@dataclass(frozen=True)
class DerivedCostRecord:
    run_id: str
    subscription_allocated_usd: Decimal
    primary_cost_usd: Decimal
    chargeable_attempt_units: int
    pool_id: str
    comparability_key: ComparabilityKey
    green: Optional[bool] = None

    def __post_init__(self) -> None:
        if self.chargeable_attempt_units < 0:
            raise CostValidationError("attempt units cannot be negative")
        object.__setattr__(self, "subscription_allocated_usd", _money(self.subscription_allocated_usd, "subscription_allocated_usd"))
        object.__setattr__(self, "primary_cost_usd", _money(self.primary_cost_usd, "primary_cost_usd"))
        if self.subscription_allocated_usd != self.primary_cost_usd:
            raise CostValidationError("P0 primary cost must equal allocated subscription cost")

    def as_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "pool_id": self.pool_id,
                "subscription_allocated_usd": _wire_decimal(self.subscription_allocated_usd),
                "primary_cost_usd": _wire_decimal(self.primary_cost_usd),
                "chargeable_attempt_units": self.chargeable_attempt_units,
                "comparability_key": self.comparability_key.as_string(), "green": self.green}


@dataclass(frozen=True)
class ClosedCostPool:
    declaration: FlatSubscriptionPoolDeclaration
    membership: ExpectedRunMembership
    records: tuple[DerivedCostRecord, ...]
    total_allocated_usd: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "total_allocated_usd", _money(self.total_allocated_usd, "total_allocated_usd"))

    @property
    def cost_to_green_usd(self) -> Optional[Decimal]:
        return cost_to_green(self.records)

    @property
    def cost_to_green(self) -> Optional[str]:
        value = self.cost_to_green_usd
        return _wire_decimal(value)


@dataclass(frozen=True)
class PoolClosureResult:
    closed: bool
    errors: tuple[str, ...] = ()
    pool: Optional[ClosedCostPool] = None

    @property
    def records(self) -> tuple[DerivedCostRecord, ...]:
        return () if self.pool is None else self.pool.records

    @property
    def total_allocated_usd(self) -> Optional[Decimal]:
        return None if self.pool is None else self.pool.total_allocated_usd

    @property
    def cost_to_green_usd(self) -> Optional[Decimal]:
        return None if self.pool is None else self.pool.cost_to_green_usd

    @property
    def cost_to_green(self) -> Optional[str]:
        return None if self.pool is None else self.pool.cost_to_green


def _allocation(pool_cost: Decimal, evidences: Sequence[RunCostEvidence]) -> tuple[Decimal, ...]:
    weights = [item.attempt_count for item in evidences]
    total_weight = sum(weights)
    if total_weight <= 0:
        raise CostValidationError("pool has zero chargeable attempt weight")
    # Work in integer cents, then largest-remainder distribute the residual
    # cents.  This is deterministic and reconciles exactly to the declared pool.
    total_cents = int((pool_cost * 100).to_integral_value(rounding=ROUND_HALF_UP))
    exact = [Decimal(total_cents) * Decimal(weight) / Decimal(total_weight) for weight in weights]
    floors = [int(value.to_integral_value(rounding=ROUND_DOWN)) for value in exact]
    remaining = total_cents - sum(floors)
    order = sorted(range(len(evidences)), key=lambda index: (-(exact[index] - floors[index]), evidences[index].run_id))
    for index in order[:remaining]:
        floors[index] += 1
    return tuple(Decimal(cents) / Decimal(100) for cents in floors)


def close_pool(
    declaration: FlatSubscriptionPoolDeclaration,
    evidences: Iterable[RunCostEvidence],
    membership: ExpectedRunMembership | None = None,
) -> PoolClosureResult:
    """Validate and, when possible, deterministically close a subscription pool."""
    members = tuple(evidences)
    expected = membership or ExpectedRunMembership.from_ids(item.run_id for item in members)
    errors: list[str] = []
    if declaration.currency != USD:
        errors.append("non-USD declaration")
    seen: dict[str, RunCostEvidence] = {}
    for item in members:
        if item.run_id in seen:
            errors.append(f"duplicate member: {item.run_id}")
            if item != seen[item.run_id]:
                errors.append(f"conflicting duplicate member: {item.run_id}")
        else:
            seen[item.run_id] = item
        if item.pool_id != declaration.pool_id:
            errors.append(f"conflicting pool_id for {item.run_id}")
        if item.declaration_digest != declaration.declaration_digest:
            errors.append(f"conflicting declaration digest: {item.run_id}")
        if tuple(item.expected_run_ids) != expected.run_ids or item.membership_digest != expected.digest:
            errors.append(f"membership digest/declaration mismatch: {item.run_id}")
        if item.currency != USD:
            errors.append(f"non-USD member: {item.run_id}")
        if item.status != "complete" or not item.terminal:
            errors.append(f"incomplete charge evidence: {item.run_id}")
        if item.generation_started and not item.chargeable_attempts:
            errors.append(f"contradictory charge evidence: {item.run_id}")
        if not item.generation_started and item.chargeable_attempts:
            errors.append(f"pre-invocation evidence has attempts: {item.run_id}")
    missing = sorted(set(expected.run_ids) - set(seen))
    unexpected = sorted(set(seen) - set(expected.run_ids))
    if missing:
        errors.append("missing members: " + ",".join(missing))
    if unexpected:
        errors.append("unexpected members: " + ",".join(unexpected))
    if len(expected.run_ids) == 0:
        errors.append("empty expected membership")
    if errors:
        return PoolClosureResult(False, tuple(dict.fromkeys(errors)))
    try:
        amounts = _allocation(declaration.pool_cost_usd, tuple(seen[run_id] for run_id in expected.run_ids))
    except CostValidationError as exc:
        return PoolClosureResult(False, (str(exc),))
    records = tuple(
        DerivedCostRecord(item.run_id, amount, amount, item.attempt_count, declaration.pool_id,
                          declaration.comparability_key, item.green)
        for item, amount in zip((seen[run_id] for run_id in expected.run_ids), amounts)
    )
    pool = ClosedCostPool(declaration, expected, records, sum(amounts, _ZERO))
    if pool.total_allocated_usd != declaration.pool_cost_usd:
        return PoolClosureResult(False, ("allocation does not reconcile to pool cost",))
    return PoolClosureResult(True, (), pool)


def close_pool_strict(
    declaration: FlatSubscriptionPoolDeclaration,
    evidences: Iterable[RunCostEvidence],
    membership: ExpectedRunMembership | None = None,
) -> ClosedCostPool:
    result = close_pool(declaration, evidences, membership)
    if not result.closed or result.pool is None:
        raise PoolClosureError(result.errors)
    return result.pool


def cost_to_green(
    records: Sequence[DerivedCostRecord],
    green_run_ids: Optional[Iterable[str]] = None,
) -> Optional[Decimal]:
    """Return total generated allocation / accepted-green count, or ``None``."""
    records = tuple(records)
    if not records:
        return None
    if green_run_ids is None:
        green = [record for record in records if record.green is True]
    else:
        green_ids = set(green_run_ids)
        green = [record for record in records if record.run_id in green_ids]
    if not green:
        return None
    total = sum((record.primary_cost_usd for record in records), _ZERO)
    return (total / Decimal(len(green))).quantize(_CENT, rounding=ROUND_HALF_UP)


__all__ = [
    "POLICY", "USD", "CLOSURE_RULE", "CHARGE_BASIS", "CostError", "CostValidationError",
    "PoolClosureError", "ExpectedRunMembership", "canonical_membership_digest",
    "ComparabilityKey", "FlatSubscriptionPoolDeclaration", "canonical_declaration_digest",
    "ChargeableAttemptReference",
    "RunCostEvidence", "DerivedCostRecord", "ClosedCostPool",
    "PoolClosureResult", "close_pool", "close_pool_strict", "cost_to_green",
    "InvocationAttemptObservation", "run_cost_evidence_from_attempts",
]
