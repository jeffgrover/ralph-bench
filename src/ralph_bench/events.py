"""Canonical, conductor-owned event recording.

Vendor streams remain raw at their adapter boundary.  This module provides the
small stable envelope used by the conductor and immutable bundle.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
import json
import time
from types import MappingProxyType
from typing import Any


EVENT_SCHEMA_VERSION = "event/v1"


class EventValidationError(ValueError):
    """Raised when an event cannot be represented by the canonical envelope."""


def _canonical_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a detached, JSON-compatible payload with deterministic semantics."""

    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise EventValidationError("event payload must be finite JSON data") from exc
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise EventValidationError("event payload must be a JSON object")
    return MappingProxyType(decoded)


@dataclass(frozen=True, slots=True)
class CanonicalEvent:
    """One normalized event ordered by a conductor-owned sequence and clock."""

    sequence: int
    time_monotonic_ms: int
    phase: str
    event_type: str
    source: str
    payload: Mapping[str, Any]
    attempt: int | None = None
    schema_version: str = EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EVENT_SCHEMA_VERSION:
            raise EventValidationError(
                f"unsupported event schema version: {self.schema_version}"
            )
        if self.sequence < 1:
            raise EventValidationError("event sequence must be positive")
        if self.time_monotonic_ms < 0:
            raise EventValidationError("monotonic event time cannot be negative")
        if not self.phase.strip() or not self.event_type.strip() or not self.source.strip():
            raise EventValidationError("event phase, type, and source are required")
        if self.attempt is not None and self.attempt < 1:
            raise EventValidationError("attempt number must be positive")
        object.__setattr__(self, "payload", _canonical_payload(self.payload))

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "time_monotonic_ms": self.time_monotonic_ms,
            "phase": self.phase,
            "attempt": self.attempt,
            "type": self.event_type,
            "source": self.source,
            "payload": deepcopy(dict(self.payload)),
        }
        return value


class EventRecorder:
    """Append-only in-memory recorder with injectable monotonic time."""

    def __init__(self, clock_ns: Callable[[], int] = time.monotonic_ns) -> None:
        self._clock_ns = clock_ns
        self._origin_ns = clock_ns()
        self._events: list[CanonicalEvent] = []

    def record(
        self,
        *,
        phase: str,
        event_type: str,
        source: str,
        payload: Mapping[str, Any] | None = None,
        attempt: int | None = None,
    ) -> CanonicalEvent:
        now_ns = self._clock_ns()
        if now_ns < self._origin_ns:
            raise EventValidationError("monotonic clock moved backwards")
        event = CanonicalEvent(
            sequence=len(self._events) + 1,
            time_monotonic_ms=(now_ns - self._origin_ns) // 1_000_000,
            phase=phase,
            event_type=event_type,
            source=source,
            attempt=attempt,
            payload=payload or {},
        )
        self._events.append(event)
        return event

    def snapshot(self) -> tuple[CanonicalEvent, ...]:
        return tuple(self._events)

    def to_jsonl(self) -> str:
        lines = [
            json.dumps(
                event.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for event in self._events
        ]
        return "" if not lines else "\n".join(lines) + "\n"
