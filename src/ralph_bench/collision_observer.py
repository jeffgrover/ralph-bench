"""Small, candidate-reported body observer for collision scoring."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, cos, hypot, isfinite, pi, sin
from typing import Any, Mapping, Sequence


EPSILON = 1e-7


@dataclass(frozen=True, slots=True)
class ObserverConfig:
    """Evidence coverage and bounded swept-collision settings."""

    maximum_gap_ms: int = 100
    maximum_sweep_steps: int = 32


@dataclass(frozen=True, slots=True)
class Body:
    id: str
    kind: str
    x: float
    y: float
    length: float
    width: float
    heading: float


def _number(value: object) -> float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) else None


def _body(raw: object, kind: str) -> Body | None:
    if not isinstance(raw, Mapping):
        return None
    values = {key: _number(raw.get(key)) for key in ("x", "y", "length", "width", "heading")}
    if not isinstance(raw.get("id"), str) or not raw["id"].strip():
        return None
    if any(value is None for value in values.values()):
        return None
    if values["length"] <= 0 or values["width"] <= 0:
        return None
    return Body(raw["id"].strip(), kind, **values)  # type: ignore[arg-type]


def _axes(body: Body) -> tuple[tuple[float, float], tuple[float, float]]:
    forward = (cos(body.heading), sin(body.heading))
    return forward, (-forward[1], forward[0])


def _corners(body: Body) -> tuple[tuple[float, float], ...]:
    forward, lateral = _axes(body)
    half_length, half_width = body.length / 2, body.width / 2
    return tuple(
        (
            body.x + forward[0] * half_length * a + lateral[0] * half_width * b,
            body.y + forward[1] * half_length * a + lateral[1] * half_width * b,
        )
        for a, b in ((-1, -1), (-1, 1), (1, -1), (1, 1))
    )


def _projection(body: Body, axis: tuple[float, float]) -> tuple[float, float]:
    values = [corner[0] * axis[0] + corner[1] * axis[1] for corner in _corners(body)]
    return min(values), max(values)


def _axes_for_pair(left: Body, right: Body) -> tuple[tuple[float, float], ...]:
    return _axes(left) + _axes(right)


def _overlaps(left: Body, right: Body) -> bool:
    for axis in _axes_for_pair(left, right):
        left_min, left_max = _projection(left, axis)
        right_min, right_max = _projection(right, axis)
        gap = max(0.0, left_min - right_max, right_min - left_max)
        if gap > EPSILON:
            return False
    return True


def _lerp_heading(start: float, end: float, fraction: float) -> float:
    delta = (end - start + pi) % (2 * pi) - pi
    return start + delta * fraction


def _interpolate(start: Body, end: Body, fraction: float) -> Body:
    return Body(
        start.id,
        start.kind,
        start.x + (end.x - start.x) * fraction,
        start.y + (end.y - start.y) * fraction,
        start.length + (end.length - start.length) * fraction,
        start.width + (end.width - start.width) * fraction,
        _lerp_heading(start.heading, end.heading, fraction),
    )


def _event(
    store: dict[tuple[str, str, str], dict[str, Any]],
    category: str,
    left: Body,
    right: Body,
    time_ms: int,
    detail: str,
) -> None:
    pair = tuple(sorted((left.id, right.id)))
    key = (category, pair[0], pair[1])
    item = store.get(key)
    if item is None:
        store[key] = {
            "category": category,
            "ids": list(pair),
            "kinds": sorted((left.kind, right.kind)),
            "first_ms": time_ms,
            "last_ms": time_ms,
            "detail": detail,
        }
        return
    item["first_ms"] = min(item["first_ms"], time_ms)
    item["last_ms"] = max(item["last_ms"], time_ms)


def analyze_observations(
    monitor: Mapping[str, Any],
    *,
    config: ObserverConfig | None = None,
) -> dict[str, Any]:
    """Analyze the optional body trace without changing load eligibility."""

    config = config or ObserverConfig()
    raw_samples = monitor.get("observations", [])
    samples = raw_samples if isinstance(raw_samples, list) else []
    raw_issued = monitor.get("issued", [])
    raw_issued = raw_issued if isinstance(raw_issued, list) else []
    issued = {
        str(item.get("id")): str(item.get("kind"))
        for item in raw_issued
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    raw_invalid = monitor.get("invalid_observations", [])
    raw_invalid = raw_invalid if isinstance(raw_invalid, list) else []
    invalid: list[dict[str, Any]] = [
        dict(item) for item in raw_invalid
        if isinstance(item, Mapping)
    ]
    normalized: list[tuple[int, dict[str, Body]]] = []
    observed_ids: set[str] = set()
    previous_time: int | None = None
    for index, raw_sample in enumerate(samples):
        if not isinstance(raw_sample, Mapping):
            invalid.append({"code": "malformed-observation", "sample": index})
            continue
        raw_time = raw_sample.get("time_ms")
        time_ms = int(raw_time) if isinstance(raw_time, (int, float)) and raw_time == raw_time else None
        raw_bodies = raw_sample.get("bodies", [])
        if time_ms is None or not isinstance(raw_bodies, list):
            invalid.append({"code": "malformed-observation", "sample": index})
            continue
        if previous_time is not None and time_ms <= previous_time:
            invalid.append({"code": "non-monotonic-observation-time", "sample": index})
            continue
        previous_time = time_ms
        body_map: dict[str, Body] = {}
        for raw_body in raw_bodies:
            body_id = raw_body.get("id") if isinstance(raw_body, Mapping) else None
            kind = issued.get(body_id)
            parsed = _body(raw_body, kind or "unknown")
            if parsed is None or kind is None:
                invalid.append({"code": "invalid-observation-body", "sample": index, "id": body_id})
                continue
            if parsed.id in body_map:
                invalid.append({"code": "duplicate-observation-id", "sample": index, "id": parsed.id})
                continue
            body_map[parsed.id] = parsed
            observed_ids.add(parsed.id)
        normalized.append((time_ms, body_map))

    collisions: dict[tuple[str, str, str], dict[str, Any]] = {}
    max_gap_ms = 0
    for sample_time, bodies in normalized:
        ids = sorted(bodies)
        for offset, left_id in enumerate(ids):
            for right_id in ids[offset + 1:]:
                left, right = bodies[left_id], bodies[right_id]
                if {left.kind, right.kind} == {"pedestrian"}:
                    continue
                if _overlaps(left, right):
                    _event(collisions, "collision", left, right, sample_time, "reported occupied footprints overlap")
    for (previous_time, previous), (current_time, current) in zip(normalized, normalized[1:]):
        delta_ms = current_time - previous_time
        max_gap_ms = max(max_gap_ms, delta_ms)
        shared = sorted(set(previous) & set(current))
        for offset, left_id in enumerate(shared):
            for right_id in shared[offset + 1:]:
                left_previous, left_current = previous[left_id], current[left_id]
                right_previous, right_current = previous[right_id], current[right_id]
                if {left_current.kind, right_current.kind} == {"pedestrian"}:
                    continue
                steps = min(config.maximum_sweep_steps, max(1, ceil(max(
                    hypot(left_current.x - left_previous.x, left_current.y - left_previous.y),
                    hypot(right_current.x - right_previous.x, right_current.y - right_previous.y),
                ) / max(0.1, min(left_current.width, right_current.width)))))
                for step in range(steps + 1):
                    fraction = step / steps
                    left = _interpolate(left_previous, left_current, fraction)
                    right = _interpolate(right_previous, right_current, fraction)
                    at_ms = round(previous_time + delta_ms * fraction)
                    if _overlaps(left, right):
                        _event(collisions, "collision", left, right, at_ms, "reported occupied footprints overlap")
                        break
                if any(item["ids"] == sorted((left_id, right_id)) for item in collisions.values()):
                    continue

    gap_times = [current - previous for (previous, _), (current, _) in zip(normalized, normalized[1:])]
    max_gap_ms = max(gap_times, default=max_gap_ms)
    missing_ids = sorted(set(issued) - observed_ids)
    coverage_complete = bool(normalized) and not missing_ids and not invalid and max_gap_ms <= config.maximum_gap_ms
    status = "unavailable" if not samples else "diagnostic"
    safety_score = (
        None
        if status == "unavailable" or not coverage_complete
        else round(100 * (0.5 ** len(collisions)), 2)
    )
    return {
        "schema_version": "collision-observations/v3",
        "status": status,
        "sample_count": len(normalized),
        "body_sample_count": sum(len(bodies) for _, bodies in normalized),
        "observed_ids": sorted(observed_ids),
        "missing_ids": missing_ids,
        "max_gap_ms": max_gap_ms,
        "coverage_complete": coverage_complete,
        "invalid_observations": invalid,
        "collisions": sorted(collisions.values(), key=lambda item: (item["first_ms"], item["ids"])),
        "collision_count": len(collisions),
        "collision_score": safety_score,
        "safety_score": safety_score,
        "collision_score_status": (
            "unavailable"
            if status == "unavailable"
            else "unmeasurable"
            if not coverage_complete
            else "scored"
        ),
        "safety_score_status": (
            "unavailable"
            if status == "unavailable"
            else "unmeasurable"
            if not coverage_complete
            else "scored"
        ),
        "config": {
            "maximum_gap_ms": config.maximum_gap_ms,
        },
    }


__all__ = ["ObserverConfig", "analyze_observations"]
