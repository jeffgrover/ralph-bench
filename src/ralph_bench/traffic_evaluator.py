"""Pure Busy Intersection checks and evaluator-facing browser transport.

The evaluator never executes candidate JavaScript itself.  A browser worker
owns that boundary and supplies snapshots/events through ``BrowserTransport``.
This module validates those observations, reconciles evaluator-issued demand,
and produces serializable assertion/capacity/recovery evidence.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .traffic import (
    DemandStage,
    NetworkDescription,
    Scenario,
    TrafficEvent,
    TrafficSnapshot,
    TrafficSchemaError,
    VehicleObservation,
    busy_intersection_network,
    build_balanced_scenario,
)


class BrowserTransport(Protocol):
    """Injectable browser boundary; implementations may wrap Playwright."""

    def load_scenario(self, scenario: Mapping[str, Any]) -> None: ...

    def reset(self, seed: int) -> None: ...

    def advance(self, simulated_milliseconds: int) -> None: ...

    def snapshot(self) -> Mapping[str, Any] | TrafficSnapshot: ...

    def drain_events(self) -> Sequence[Mapping[str, Any] | TrafficEvent]: ...


def _transport_call(transport: object, method_name: str, *args: Any) -> Any:
    """Call the Python adapter spelling, accepting the browser camelCase too."""

    method = getattr(transport, method_name, None)
    if method is None:
        parts = method_name.split("_")
        camel_name = parts[0] + "".join(part.title() for part in parts[1:])
        method = getattr(transport, camel_name, None)
    if not callable(method):
        raise TypeError(f"browser transport is missing {method_name}()")
    return method(*args)


@dataclass(frozen=True, slots=True)
class CandidateCheckResult:
    passed: bool
    checks: tuple[dict[str, Any], ...]
    entrypoint: str = "index.html"
    tree_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "entrypoint": self.entrypoint,
            "tree_hash": self.tree_hash,
            "checks": [dict(item) for item in self.checks],
        }


def check_static_candidate(candidate_root: str | Path) -> CandidateCheckResult:
    """Check the public, technology-neutral static artifact contract.

    This is intentionally a structural/public check.  It does not decide
    whether traffic is safe; those assertions require private browser
    observations.  External URLs, symlinks, and a missing traffic bridge are
    rejected because they make a submission non-reproducible offline.
    """

    root = Path(candidate_root)
    checks: list[dict[str, Any]] = []

    def add(check_id: str, passed: bool, detail: str) -> None:
        checks.append({"id": check_id, "result": "pass" if passed else "fail", "detail": detail})

    if not root.is_dir() or root.is_symlink():
        add("submission-directory", False, "submission must be a real directory")
        return CandidateCheckResult(False, tuple(checks))
    files: list[Path] = []
    unsafe = False
    for current, directories, names in __import__("os").walk(root, followlinks=False):
        current_path = Path(current)
        for name in directories + names:
            path = current_path / name
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                unsafe = True
            elif path.is_file():
                files.append(path)
    add("submission-files", not unsafe, "all submission entries are regular files/directories")
    entrypoint = root / "index.html"
    if not entrypoint.is_file() or entrypoint.is_symlink():
        add("entrypoint", False, "index.html is required")
        return CandidateCheckResult(False, tuple(checks))
    try:
        source = entrypoint.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        add("entrypoint-readable", False, f"index.html is not UTF-8 readable: {exc}")
        return CandidateCheckResult(False, tuple(checks))
    add("entrypoint", True, "index.html is present and readable")
    external = re.compile(r"(?:https?:|wss?:|//)[^\s'\"<>]+", re.IGNORECASE).search(source)
    add("offline-runtime", external is None, "no external network URL is referenced")
    has_bridge = "__RALPH_BENCH__" in source and "traffic/v1" in source
    add("traffic-bridge", has_bridge, "traffic/v1 browser bridge is declared")
    add("no-backend", not bool(re.search(r"\b(?:WebSocket|EventSource)\s*\(", source)), "no backend transport is required")
    tree_hash: str | None = None
    try:
        import hashlib
        digest = hashlib.sha256()
        for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root).as_posix().encode("utf-8")
            data = path.read_bytes()
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            digest.update(len(data).to_bytes(8, "big"))
            digest.update(data)
        tree_hash = digest.hexdigest()
    except OSError:
        pass
    return CandidateCheckResult(not any(item["result"] == "fail" for item in checks), tuple(checks), tree_hash=tree_hash)


# Descriptive aliases keep the public boundary pleasant for challenge callers.
check_candidate = check_static_candidate
validate_candidate = check_static_candidate


@dataclass(frozen=True, slots=True)
class EvaluationThresholds:
    """Calibratable judge limits; safety limits remain non-negotiable."""

    max_wait_ms: int = 180_000
    max_backlog: int = 60
    max_queue_storage_fraction: float = 1.0
    minimum_completion_ratio: float = 0.75
    recovery_queue_fraction: float = 0.05
    # A request may not sit unadmitted past this bound while the scenario is
    # still running.  This is deliberately independent of service time.
    max_admission_wait_ms: int = 180_000


@dataclass(frozen=True, slots=True)
class AssertionResult:
    assertion_id: str
    severity: str
    result: str
    detector: str
    detail: str
    evidence_refs: tuple[str, ...] = ()
    scenario_id: str | None = None
    seed: int | None = None
    threshold: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "severity": self.severity,
            "result": self.result,
            "detector": self.detector,
            "detail": self.detail,
            "evidence_refs": list(self.evidence_refs),
            "scenario_id": self.scenario_id,
            "seed": self.seed,
            "threshold": dict(self.threshold),
        }


@dataclass(frozen=True, slots=True)
class FailureRecord:
    code: str
    severity: str
    stage_id: str | None
    detail: str
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity, "stage_id": self.stage_id, "detail": self.detail, "evidence_refs": list(self.evidence_refs)}


@dataclass(frozen=True, slots=True)
class CapacityStageResult:
    stage_id: str
    offered_trips_per_hour: int
    requested: int
    admitted: int
    completed: int
    valid_completed: int
    backlog: int
    max_queue_m: float
    max_wait_ms: int | None
    qualifying: bool
    failure_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "offered_trips_per_hour": self.offered_trips_per_hour,
            "requested": self.requested,
            "admitted": self.admitted,
            "completed": self.completed,
            "valid_completed": self.valid_completed,
            "backlog": self.backlog,
            "max_queue_m": self.max_queue_m,
            "max_wait_ms": self.max_wait_ms,
            "qualifying": self.qualifying,
            "failure_codes": list(self.failure_codes),
        }


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    attempted: bool
    passed: bool
    queue_clear_time_ms: int | None
    stranded_trips: int
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"attempted": self.attempted, "passed": self.passed, "queue_clear_time_ms": self.queue_clear_time_ms, "stranded_trips": self.stranded_trips, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    challenge: str
    scenario_id: str
    seed: int
    outcome: str
    assertions: tuple[AssertionResult, ...]
    capacity_curve: tuple[CapacityStageResult, ...]
    failures: tuple[FailureRecord, ...]
    recovery: RecoveryResult
    runtime_observations: tuple[dict[str, Any], ...]
    metrics: Mapping[str, Any]

    @property
    def passed(self) -> bool:
        return self.outcome == "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "challenge": self.challenge,
            "scenario_id": self.scenario_id,
            "seed": self.seed,
            "outcome": self.outcome,
            "assertions": [item.to_dict() for item in self.assertions],
            "capacity_curve": [item.to_dict() for item in self.capacity_curve],
            "failures": [item.to_dict() for item in self.failures],
            "recovery": self.recovery.to_dict(),
            "runtime_observations": [dict(item) for item in self.runtime_observations],
            "metrics": dict(self.metrics),
        }


def _assert(
    assertion_id: str,
    passed: bool,
    *,
    severity: str = "critical",
    detector: str = "traffic/v1",
    detail: str,
    scenario: Scenario,
    refs: Sequence[str] = (),
    threshold: Mapping[str, Any] | None = None,
) -> AssertionResult:
    return AssertionResult(assertion_id, severity, "pass" if passed else "fail", detector, detail, tuple(refs), scenario.scenario_id, scenario.seed, threshold or {})


def validate_network(network: NetworkDescription, scenario: Scenario | None = None) -> tuple[AssertionResult, ...]:
    """Validate the connected movement graph and fixed physical envelope."""

    scenario = scenario or build_balanced_scenario()
    nodes = set(network.nodes)
    lane_ids = {lane.id for lane in network.lane_segments}
    movement_ids = {movement.id for movement in network.movements}
    approaches = {lane.approach for lane in network.lane_segments}
    turns = {movement.turn for movement in network.movements}
    refs = tuple(f"network:{item}" for item in sorted(movement_ids))
    return (
        _assert("connected-movement-graph", bool(nodes) and all(m.origin in nodes and m.destination in nodes and m.lane_segments and set(m.lane_segments) <= lane_ids for m in network.movements), detail=f"{len(network.movements)} movements use declared nodes and lanes", scenario=scenario, refs=refs),
        _assert("complete-turn-mix", {"left", "straight", "right"} <= turns, severity="major", detail="left, straight, and right movements are present", scenario=scenario, refs=refs),
        _assert("four-approaches", len(approaches) >= 4 and len(network.crossings) >= 4, detail="four approaches and crossings are declared", scenario=scenario),
        _assert("physical-envelope", not network.grade_separation and network.vehicle_length_m > 0 and network.minimum_headway_m > 0, detail="vehicle, headway, and grade-separation constraints are bounded", scenario=scenario),
    )


def validate_network_compatibility(
    expected: NetworkDescription,
    described: NetworkDescription | None,
    scenario: Scenario,
    *,
    error: str | None = None,
) -> tuple[AssertionResult, ...]:
    """Check candidate ``describeNetwork`` evidence against evaluator limits.

    The evaluator-owned network remains authoritative for all observations.
    Candidate geometry may be equal to or smaller than the fixed envelope,
    but it cannot add capacity, remove movements, shrink vehicles, or raise
    speeds/acceleration.  A malformed description is a critical failure.
    """

    if described is None:
        detail = error or "candidate did not provide a valid network description"
        return (_assert("network-compatibility", False, detail=detail, scenario=scenario),)
    if error:
        return (_assert("network-compatibility", False, detail=error, scenario=scenario),)
    compatible = True
    details: list[str] = []
    if described.api_version != expected.api_version:
        compatible = False
        details.append("protocol mismatch")
    if described.nodes != expected.nodes:
        compatible = False
        details.append("nodes differ")
    expected_lanes = {lane.id: lane for lane in expected.lane_segments}
    described_lanes = {lane.id: lane for lane in described.lane_segments}
    if set(described_lanes) != set(expected_lanes):
        compatible = False
        details.append("lane IDs differ")
    for lane_id, expected_lane in expected_lanes.items():
        candidate_lane = described_lanes.get(lane_id)
        if candidate_lane is None:
            continue
        if candidate_lane.approach != expected_lane.approach or candidate_lane.direction != expected_lane.direction:
            compatible = False
            details.append(f"lane {lane_id} identity differs")
        if candidate_lane.length_m > expected_lane.length_m + 0.01:
            compatible = False
            details.append(f"lane {lane_id} exceeds fixed length")
        if candidate_lane.speed_limit_mps > expected_lane.speed_limit_mps + 0.01:
            compatible = False
            details.append(f"lane {lane_id} exceeds fixed speed")
        if candidate_lane.storage_m > expected_lane.storage_m + 0.01:
            compatible = False
            details.append(f"lane {lane_id} exceeds fixed storage")
    expected_movements = {movement.id: movement for movement in expected.movements}
    described_movements = {movement.id: movement for movement in described.movements}
    if set(described_movements) != set(expected_movements):
        compatible = False
        details.append("movement IDs differ")
    for movement_id, expected_movement in expected_movements.items():
        candidate_movement = described_movements.get(movement_id)
        if candidate_movement is None:
            continue
        if (
            candidate_movement.origin != expected_movement.origin
            or candidate_movement.destination != expected_movement.destination
            or candidate_movement.turn != expected_movement.turn
            or candidate_movement.lane_segments != expected_movement.lane_segments
        ):
            compatible = False
            details.append(f"movement {movement_id} differs")
    expected_crossings = {crossing.id: crossing for crossing in expected.crossings}
    described_crossings = {crossing.id: crossing for crossing in described.crossings}
    if set(described_crossings) != set(expected_crossings):
        compatible = False
        details.append("crossing IDs differ")
    for crossing_id, expected_crossing in expected_crossings.items():
        candidate_crossing = described_crossings.get(crossing_id)
        if candidate_crossing is not None and (
            candidate_crossing.approach != expected_crossing.approach
            or candidate_crossing.length_m > expected_crossing.length_m + 0.01
        ):
            compatible = False
            details.append(f"crossing {crossing_id} exceeds fixed envelope")
    if described.vehicle_length_m + 0.01 < expected.vehicle_length_m:
        compatible = False
        details.append("vehicle length is smaller than the fixed envelope")
    if described.max_acceleration_mps2 > expected.max_acceleration_mps2 + 0.01:
        compatible = False
        details.append("acceleration exceeds the fixed envelope")
    if described.comfortable_braking_mps2 > expected.comfortable_braking_mps2 + 0.01:
        compatible = False
        details.append("braking exceeds the fixed envelope")
    if described.minimum_headway_m + 0.01 < expected.minimum_headway_m:
        compatible = False
        details.append("headway is smaller than the fixed envelope")
    if described.grade_separation:
        compatible = False
        details.append("grade separation is prohibited")
    return (
        _assert(
            "network-compatibility",
            compatible,
            detail="candidate network is within the evaluator-owned envelope"
            if compatible
            else "; ".join(details),
            scenario=scenario,
        ),
    )


def _snapshot_assertions(snapshot: TrafficSnapshot, previous: TrafficSnapshot | None, network: NetworkDescription, scenario: Scenario, thresholds: EvaluationThresholds) -> tuple[AssertionResult, ...]:
    lane_by_id = {lane.id: lane for lane in network.lane_segments}
    movement_by_id = {movement.id: movement for movement in network.movements}
    vehicle_ids = [vehicle.trip_id for vehicle in snapshot.vehicles]
    duplicate_vehicle = len(set(vehicle_ids)) != len(vehicle_ids)
    bad_lane = False
    speed_violation = False
    for vehicle in snapshot.vehicles:
        lane = lane_by_id.get(vehicle.lane_segment_id)
        movement = movement_by_id.get(vehicle.movement_id)
        if lane is None or movement is None or vehicle.lane_segment_id not in movement.lane_segments or vehicle.position_m > lane.length_m:
            bad_lane = True
        if lane is not None and vehicle.speed_mps > lane.speed_limit_mps + 0.01:
            speed_violation = True
    overlaps: list[str] = []
    by_lane: dict[str, list[VehicleObservation]] = defaultdict(list)
    for vehicle in snapshot.vehicles:
        by_lane[vehicle.lane_segment_id].append(vehicle)
    for lane_id, vehicles in by_lane.items():
        ordered = sorted(vehicles, key=lambda item: item.position_m)
        for first, second in zip(ordered, ordered[1:]):
            if second.position_m - first.position_m < (first.length_m + second.length_m) / 2:
                overlaps.append(f"{lane_id}:{first.trip_id}:{second.trip_id}")
    monotonic = previous is None or snapshot.time_ms >= previous.time_ms
    queue_storage_ok = True
    storage_by_approach = {lane.approach: lane.storage_m for lane in network.lane_segments if lane.direction == "inbound"}
    for queue in snapshot.queues:
        if queue.length_m > storage_by_approach.get(queue.approach, 0) * thresholds.max_queue_storage_fraction + 0.01:
            queue_storage_ok = False
    return (
        _assert("snapshot-time-monotonic", monotonic, detail="snapshot time does not move backwards", scenario=scenario),
        _assert("lane-and-path-adherence", not bad_lane, detail="vehicles remain on declared movement lanes", scenario=scenario),
        _assert("bounded-speed", not speed_violation, detail="vehicle speed remains below the lane limit", scenario=scenario),
        _assert("no-overlap", not duplicate_vehicle and not overlaps, detail="vehicles have unique IDs and non-overlapping envelopes", scenario=scenario, refs=tuple(f"snapshot:{snapshot.time_ms}" for _ in overlaps)),
        _assert("no-red-entry", not any(vehicle.entered_on_red for vehicle in snapshot.vehicles), detail="no vehicle reports entry on red", scenario=scenario),
        _assert("queue-storage", queue_storage_ok, severity="major", detail="queues remain within declared storage", scenario=scenario),
        _assert("browser-runtime", not snapshot.runtime_errors, detail="browser snapshot has no runtime errors", scenario=scenario),
    )


def _event_assertions(events: Sequence[TrafficEvent], scenario: Scenario) -> tuple[AssertionResult, ...]:
    known_bad = {"collision", "vehicle_pedestrian_conflict", "red_light_entry", "teleportation", "trip.lost", "invalid_disappearance", "runtime.error"}
    bad = [event for event in events if event.event_type in known_bad]
    sequences = [event.sequence for event in events]
    times = [event.time_ms for event in events]
    departures = {trip.trip_id: trip.departure_ms for trip in scenario.trips}
    request_time_ok = all(
        event.time_ms >= departures[event.entity_id]
        for event in events
        if event.entity_id in departures and (event.event_type.startswith("trip.") or event.event_type.startswith("vehicle."))
    )
    return (
        _assert("event-order", sequences == sorted(set(sequences)) and times == sorted(times), detail="events have unique monotonic sequence and time order", scenario=scenario),
        _assert("event-request-time", request_time_ok, detail="trip and vehicle lifecycle events do not precede their request", scenario=scenario),
        _assert("no-safety-events", not bad, detail="no collision, conflict, red-entry, teleport, or loss event occurred", scenario=scenario, refs=tuple(f"event:{event.sequence}" for event in bad)),
    )


def _trip_reconciliation(scenario: Scenario, snapshots: Sequence[TrafficSnapshot], events: Sequence[TrafficEvent], thresholds: EvaluationThresholds) -> tuple[tuple[AssertionResult, ...], dict[str, Any], set[str]]:
    requested = {trip.trip_id for trip in scenario.trips}
    trip_by_id = {trip.trip_id: trip for trip in scenario.trips}
    known = requested | {item.trip_id for snapshot in snapshots for item in snapshot.trips}
    admitted: set[str] = set()
    completed: set[str] = set()
    rejected: set[str] = set()
    lost: set[str] = set()
    unknown: set[str] = set()
    event_types: dict[str, set[str]] = defaultdict(set)
    event_times: dict[tuple[str, str], list[int]] = defaultdict(list)
    for event in events:
        if event.entity_id in requested:
            event_types[event.entity_id].add(event.event_type)
            event_times[(event.entity_id, event.event_type)].append(event.time_ms)
        if event.event_type.startswith("trip."):
            if event.entity_id not in known:
                unknown.add(event.entity_id)
            if event.event_type == "trip.admitted":
                admitted.add(event.entity_id)
            elif event.event_type == "trip.completed":
                completed.add(event.entity_id)
            elif event.event_type == "trip.rejected":
                rejected.add(event.entity_id)
            elif event.event_type == "trip.lost":
                lost.add(event.entity_id)
    final_trips: dict[str, str] = {}
    for snapshot in snapshots:
        for trip in snapshot.trips:
            if trip.trip_id not in requested:
                unknown.add(trip.trip_id)
            final_trips[trip.trip_id] = trip.status
            if trip.status in {"admitted", "active", "completed"}:
                admitted.add(trip.trip_id)
            if trip.status == "completed":
                completed.add(trip.trip_id)
            elif trip.status == "explicitly_rejected":
                rejected.add(trip.trip_id)
            elif trip.status == "lost":
                lost.add(trip.trip_id)
    accounted = admitted | rejected | lost | set(final_trips)
    missing = requested - accounted
    duplicate_completion = [trip_id for trip_id in completed if sum(event.event_type == "trip.completed" and event.entity_id == trip_id for event in events) > 1]
    lifecycle_failures: list[str] = []
    admission_waits: list[int] = []
    incompletion_waits: list[int] = []
    for trip_id, trip in trip_by_id.items():
        types = event_types.get(trip_id, set())
        if trip_id in rejected or trip_id in lost:
            continue
        # Status fields are only corroboration.  A terminal trip must show a
        # physical traversal, not merely a fabricated completed counter.
        if trip_id in admitted or trip_id in completed:
            admission_times = event_times.get((trip_id, "trip.admitted"), [])
            entered_times = event_times.get((trip_id, "vehicle.entered"), [])
            exited_times = event_times.get((trip_id, "vehicle.exited"), [])
            if not admission_times:
                lifecycle_failures.append(f"{trip_id}:missing-admission-event")
            else:
                admission_waits.append(min(admission_times) - trip.departure_ms)
            if not entered_times:
                lifecycle_failures.append(f"{trip_id}:missing-vehicle-entry")
            if trip_id in completed and not exited_times:
                lifecycle_failures.append(f"{trip_id}:missing-vehicle-exit")
            observations = [vehicle for snapshot in snapshots for vehicle in snapshot.vehicles if vehicle.trip_id == trip_id]
            positions = {vehicle.position_m for vehicle in observations}
            if len(positions) < 2 or max(positions, default=0.0) - min(positions, default=0.0) < 0.5:
                lifecycle_failures.append(f"{trip_id}:missing-physical-trajectory")
            if trip_id in completed:
                completed_times = event_times.get((trip_id, "trip.completed"), [])
                if not completed_times:
                    lifecycle_failures.append(f"{trip_id}:missing-completion-event")
                elif exited_times and min(completed_times) < min(exited_times):
                    lifecycle_failures.append(f"{trip_id}:completion-before-exit")
        elif trip_id in final_trips and final_trips[trip_id] == "requested":
            lifecycle_failures.append(f"{trip_id}:never-admitted")
        if trip_id not in completed and trip_id not in rejected and trip_id not in lost:
            incompletion_waits.append(max(0, scenario.horizon_ms - trip.departure_ms))
    overdue_incomplete = [
        trip_id for trip_id, waited in zip(
            (trip.trip_id for trip in scenario.trips if trip.trip_id not in completed and trip.trip_id not in rejected and trip.trip_id not in lost),
            incompletion_waits,
        ) if waited >= thresholds.max_admission_wait_ms
    ]
    assertions = (
        _assert("requested-trip-reconciliation", not missing and not unknown, detail=f"requested={len(requested)}, accounted={len(accounted)}, missing={len(missing)}, unknown={len(unknown)}", scenario=scenario),
        _assert("no-lost-trips", not lost, detail=f"lost trips: {len(lost)}", scenario=scenario, refs=tuple(f"trip:{item}" for item in sorted(lost))),
        _assert("no-duplicate-completions", not duplicate_completion, detail="each trip completes at most once", scenario=scenario),
        _assert("physical-trip-lifecycle", not lifecycle_failures, detail="; ".join(lifecycle_failures) if lifecycle_failures else "requested trips have physical admission, trajectory, and exit evidence", scenario=scenario, refs=tuple(f"trip:{item.split(':', 1)[0]}" for item in lifecycle_failures)),
        _assert("bounded-admission-wait", not admission_waits or max(admission_waits) <= thresholds.max_admission_wait_ms, severity="major", detail="request-to-admission waits remain bounded" if not admission_waits or max(admission_waits) <= thresholds.max_admission_wait_ms else f"maximum admission wait: {max(admission_waits)}ms", scenario=scenario, threshold={"max_wait_ms": thresholds.max_admission_wait_ms}),
        _assert("bounded-incompletion-wait", not overdue_incomplete, severity="major", detail="no request remained incomplete beyond the bounded horizon wait" if not overdue_incomplete else f"overdue incomplete trips: {len(overdue_incomplete)}", scenario=scenario, refs=tuple(f"trip:{item}" for item in overdue_incomplete), threshold={"max_wait_ms": thresholds.max_admission_wait_ms}),
    )
    metrics = {"requested": len(requested), "admitted": len(admitted), "completed": len(completed), "rejected": len(rejected), "lost": len(lost), "outstanding": len(requested - completed - rejected - lost), "max_admission_wait_ms": max(admission_waits, default=None)}
    return assertions, metrics, completed - lost


def _stage_results(scenario: Scenario, snapshots: Sequence[TrafficSnapshot], events: Sequence[TrafficEvent], valid_completed: set[str], thresholds: EvaluationThresholds) -> tuple[CapacityStageResult, ...]:
    results: list[CapacityStageResult] = []
    for stage in scenario.stages:
        requested_ids = {trip.trip_id for trip in scenario.trips if stage.start_ms <= trip.departure_ms < stage.end_ms}
        # Requests belong to their offered stage. Their admission/completion
        # may occur later, so use the complete event stream but restrict every
        # count to this stage's request cohort. This prevents cumulative event
        # counts (and cooldown demand) from contaminating the capacity curve.
        cohort_events = [event for event in events if event.entity_id in requested_ids]
        admitted_ids = {event.entity_id for event in cohort_events if event.event_type == "trip.admitted"}
        completed_ids = {event.entity_id for event in cohort_events if event.event_type == "trip.completed"}
        snapshots_in_stage = [snapshot for snapshot in snapshots if stage.start_ms <= snapshot.time_ms <= stage.end_ms]
        cohort_snapshots = snapshots
        for snapshot in cohort_snapshots:
            for trip in snapshot.trips:
                if trip.trip_id in requested_ids and trip.status in {"admitted", "active", "completed"}:
                    admitted_ids.add(trip.trip_id)
                if trip.trip_id in requested_ids and trip.status == "completed":
                    completed_ids.add(trip.trip_id)
        queue_max = max((queue.length_m for snapshot in snapshots_in_stage for queue in snapshot.queues), default=0.0)
        waits: list[int] = []
        for event in cohort_events:
            if event.event_type == "trip.completed":
                admitted_event = next((candidate for candidate in events if candidate.entity_id == event.entity_id and candidate.event_type == "trip.admitted" and candidate.time_ms <= event.time_ms), None)
                if admitted_event is not None:
                    waits.append(event.time_ms - admitted_event.time_ms)
        max_wait = max(waits) if waits else None
        backlog = max(0, len(requested_ids) - len(admitted_ids))
        failures: list[str] = []
        if stage.qualifying and backlog > thresholds.max_backlog:
            failures.append("backlog-growth")
        if stage.qualifying and max_wait is not None and max_wait > thresholds.max_wait_ms:
            failures.append("service-wait")
        request_admission_waits = [
            event.time_ms - trip.departure_ms
            for trip in scenario.trips
            if trip.trip_id in requested_ids
            for event in cohort_events
            if event.entity_id == trip.trip_id and event.event_type == "trip.admitted"
        ]
        if stage.qualifying and request_admission_waits and max(request_admission_waits) > thresholds.max_admission_wait_ms:
            failures.append("admission-wait")
        if stage.qualifying and requested_ids and len(completed_ids) / len(requested_ids) < thresholds.minimum_completion_ratio:
            failures.append("completion-ratio")
        # A movement with demand but no admitted request is starvation, even
        # when the aggregate intersection ratio happens to look healthy.
        movement_ids = {trip.movement_id for trip in scenario.trips if trip.trip_id in requested_ids}
        for movement_id in movement_ids:
            movement_requested = {trip.trip_id for trip in scenario.trips if trip.trip_id in requested_ids and trip.movement_id == movement_id}
            movement_admitted = admitted_ids & movement_requested
            if stage.qualifying and movement_requested and not movement_admitted:
                failures.append(f"movement-starvation:{movement_id}")
            movement_completed = completed_ids & movement_requested
            if stage.qualifying and movement_requested and len(movement_completed) / len(movement_requested) < thresholds.minimum_completion_ratio:
                failures.append(f"movement-fairness:{movement_id}")
        qualifying = stage.qualifying and not failures
        results.append(CapacityStageResult(stage.id, stage.offered_trips_per_hour, len(requested_ids), len(admitted_ids), len(completed_ids), len(completed_ids & valid_completed), backlog, queue_max, max_wait, qualifying, tuple(failures)))
    return tuple(results)


def _recovery(scenario: Scenario, snapshots: Sequence[TrafficSnapshot], capacity: Sequence[CapacityStageResult]) -> RecoveryResult:
    cooldown = [stage for stage in scenario.stages if stage.cooldown]
    if not cooldown:
        return RecoveryResult(False, False, None, 0, "scenario has no cooldown stage")
    first = cooldown[0]
    cooldown_snapshots = [snapshot for snapshot in snapshots if first.start_ms <= snapshot.time_ms <= first.end_ms]
    if not cooldown_snapshots:
        return RecoveryResult(True, False, None, 0, "no observations were recorded during cooldown")
    queue_counts = [sum(queue.vehicle_count for queue in snapshot.queues) for snapshot in cooldown_snapshots]
    clear_time = next((snapshot.time_ms - first.start_ms for snapshot, count in zip(cooldown_snapshots, queue_counts) if count == 0), None)
    final = cooldown_snapshots[-1]
    stranded = sum(trip.status in {"active", "admitted", "lost"} for trip in final.trips)
    passed = clear_time is not None and stranded == 0
    return RecoveryResult(True, passed, clear_time, stranded, "queues cleared and no trips remained stranded" if passed else "cooldown ended with uncleared queues or stranded trips")


def evaluate_observations(
    scenario: Scenario | Mapping[str, Any],
    network: NetworkDescription | Mapping[str, Any],
    snapshots: Iterable[TrafficSnapshot | Mapping[str, Any]],
    events: Iterable[TrafficEvent | Mapping[str, Any]],
    thresholds: EvaluationThresholds | None = None,
    *,
    candidate_network: NetworkDescription | Mapping[str, Any] | None = None,
    candidate_network_error: str | None = None,
) -> EvaluationResult:
    """Reconcile browser observations into deterministic P0-A evidence."""

    scenario = scenario if isinstance(scenario, Scenario) else Scenario.from_dict(scenario)
    network = network if isinstance(network, NetworkDescription) else NetworkDescription.from_dict(network)
    thresholds = thresholds or EvaluationThresholds()
    parsed_snapshots = tuple(item if isinstance(item, TrafficSnapshot) else TrafficSnapshot.from_dict(item) for item in snapshots)
    parsed_events = tuple(item if isinstance(item, TrafficEvent) else TrafficEvent.from_dict(item) for item in events)
    # Preserve transport order for protocol assertions.  Derive sorted views
    # only for metrics so a candidate cannot hide a time reversal by sorting
    # its own evidence before it reaches the judge.
    ordered_snapshots = parsed_snapshots
    ordered_events = parsed_events
    aggregate_snapshots = tuple(sorted(parsed_snapshots, key=lambda item: item.time_ms))
    aggregate_events = tuple(sorted(parsed_events, key=lambda item: (item.sequence, item.time_ms)))
    assertions: list[AssertionResult] = list(validate_network(network, scenario))
    if candidate_network is not None or candidate_network_error is not None:
        described = candidate_network
        if described is not None and not isinstance(described, NetworkDescription):
            try:
                described = NetworkDescription.from_dict(described)
            except (TypeError, TrafficSchemaError, ValueError) as exc:
                described = None
                candidate_network_error = candidate_network_error or f"malformed describeNetwork result: {exc}"
        assertions.extend(validate_network_compatibility(network, described, scenario, error=candidate_network_error))
    previous: TrafficSnapshot | None = None
    for snapshot in ordered_snapshots:
        assertions.extend(_snapshot_assertions(snapshot, previous, network, scenario, thresholds))
        previous = snapshot
    assertions.extend(_event_assertions(ordered_events, scenario))
    reconciliation, lifecycle_metrics, valid_completed = _trip_reconciliation(scenario, aggregate_snapshots, aggregate_events, thresholds)
    assertions.extend(reconciliation)
    capacity = _stage_results(scenario, aggregate_snapshots, aggregate_events, valid_completed, thresholds)
    failures: list[FailureRecord] = []
    for assertion in assertions:
        if assertion.result == "fail":
            failures.append(FailureRecord(assertion.assertion_id, assertion.severity, None, assertion.detail, assertion.evidence_refs))
    for stage in capacity:
        for code in stage.failure_codes:
            failures.append(FailureRecord(code, "major", stage.stage_id, f"stage {stage.stage_id} failed {code}"))
    recovery = _recovery(scenario, aggregate_snapshots, capacity)
    if recovery.attempted and not recovery.passed:
        failures.append(FailureRecord("recovery-failure", "major", "cooldown", recovery.detail))
    critical_failures = [item for item in failures if item.severity == "critical"]
    outcome = "passed" if not failures and all(not stage.qualifying or stage.qualifying for stage in capacity) and recovery.passed else "failed"
    metrics = {
        **lifecycle_metrics,
        "peak_valid_throughput": max((stage.valid_completed / next((item.duration_ms for item in scenario.stages if item.id == stage.stage_id), 1) * 3_600_000 for stage in capacity if stage.qualifying), default=0),
        "last_qualifying_stage": next((stage.stage_id for stage in reversed(capacity) if stage.qualifying), None),
        "first_failure_stage": next((stage.stage_id for stage in capacity if stage.failure_codes), None),
        "critical_failure_count": len(critical_failures),
        "snapshot_count": len(ordered_snapshots),
        "event_count": len(ordered_events),
    }
    return EvaluationResult("busy-intersection/v1", scenario.scenario_id, scenario.seed, outcome, tuple(assertions), capacity, tuple(failures), recovery, tuple({"time_ms": snapshot.time_ms, "vehicle_count": len(snapshot.vehicles), "queue_count": len(snapshot.queues), "runtime_errors": list(snapshot.runtime_errors)} for snapshot in ordered_snapshots), metrics)


def evaluate_transport(
    transport: BrowserTransport,
    scenario: Scenario | Mapping[str, Any],
    network: NetworkDescription | Mapping[str, Any] | None = None,
    *,
    step_ms: int = 1_000,
    thresholds: EvaluationThresholds | None = None,
    candidate_network: NetworkDescription | Mapping[str, Any] | None = None,
    candidate_network_error: str | None = None,
) -> EvaluationResult:
    """Drive an injected browser transport with deterministic fixed steps."""

    scenario = scenario if isinstance(scenario, Scenario) else Scenario.from_dict(scenario)
    network = network or busy_intersection_network()
    network = network if isinstance(network, NetworkDescription) else NetworkDescription.from_dict(network)
    if step_ms < 1:
        raise ValueError("step_ms must be positive")
    snapshots: list[TrafficSnapshot] = []
    events: list[TrafficEvent] = []
    try:
        _transport_call(transport, "load_scenario", scenario.to_dict())
        _transport_call(transport, "reset", scenario.seed)
        raw_initial_snapshot = _transport_call(transport, "snapshot")
        snapshots.append(raw_initial_snapshot if isinstance(raw_initial_snapshot, TrafficSnapshot) else TrafficSnapshot.from_dict(raw_initial_snapshot))
        for stage in scenario.stages:
            current = stage.start_ms
            while current < stage.end_ms:
                advance_by = min(step_ms, stage.end_ms - current)
                _transport_call(transport, "advance", advance_by)
                current += advance_by
                raw_snapshot = _transport_call(transport, "snapshot")
                snapshots.append(raw_snapshot if isinstance(raw_snapshot, TrafficSnapshot) else TrafficSnapshot.from_dict(raw_snapshot))
                raw_events = _transport_call(transport, "drain_events")
                events.extend(item if isinstance(item, TrafficEvent) else TrafficEvent.from_dict(item) for item in raw_events)
                # A bridge must drain atomically.  Preserve a second immediate
                # batch as evidence and turn it into a critical protocol event;
                # otherwise a candidate could hide lifecycle/safety events in
                # a deferred queue that the judge never observes.
                residual = _transport_call(transport, "drain_events")
                if residual:
                    events.extend(item if isinstance(item, TrafficEvent) else TrafficEvent.from_dict(item) for item in residual)
                    next_sequence = max((item.sequence for item in events), default=-1) + 1
                    events.append(TrafficEvent(next_sequence, current, "runtime.error", "browser", {"error_type": "drain_residual", "count": len(residual)}))
    except Exception as exc:
        snapshots.append(TrafficSnapshot(scenario.horizon_ms, runtime_errors=(f"transport:{type(exc).__name__}: {exc}",)))
        events.append(TrafficEvent(len(events), scenario.horizon_ms, "runtime.error", "browser", {"error_type": type(exc).__name__}))
    return evaluate_observations(
        scenario,
        network,
        snapshots,
        events,
        thresholds,
        candidate_network=candidate_network,
        candidate_network_error=candidate_network_error,
    )


__all__ = [
    "BrowserTransport", "CandidateCheckResult", "check_static_candidate", "check_candidate", "validate_candidate", "EvaluationThresholds",
    "AssertionResult", "FailureRecord", "CapacityStageResult", "RecoveryResult", "EvaluationResult",
    "validate_network", "validate_network_compatibility", "evaluate_observations", "evaluate_transport",
]
