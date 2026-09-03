"""Public artifact checks and evaluator-owned ``gates/v1`` monitoring."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import re
from statistics import median
from typing import Any, Mapping, Sequence

from .gates import DemandStage, GateScenario


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


_EXTERNAL_REFERENCE = re.compile(
    r"""(?:
        \b(?:src|href)\s*=\s*["']\s*(?:https?:)?//
      | \b(?:fetch|WebSocket|EventSource|importScripts)\s*\(\s*["']\s*(?:https?:)?//
      | \bimport\s+(?:[^"']+?\s+from\s+)?["']\s*(?:https?:)?//
      | \burl\s*\(\s*["']?\s*(?:https?:)?//
      | @import\s+["']\s*(?:https?:)?//
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def check_static_candidate(candidate_root: str | Path) -> CandidateCheckResult:
    """Validate the small public static/offline gates/v1 contract."""

    root = Path(candidate_root)
    checks: list[dict[str, Any]] = []

    def add(check_id: str, passed: bool, success: str, failure: str) -> None:
        checks.append(
            {
                "id": check_id,
                "result": "pass" if passed else "fail",
                "detail": success if passed else failure,
            }
        )

    if not root.is_dir() or root.is_symlink():
        add("submission-directory", False, "submission directory is valid", "submission must be a real directory")
        return CandidateCheckResult(False, tuple(checks))
    files: list[Path] = []
    unsafe: list[str] = []
    for current, directories, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in directories + names:
            path = current_path / name
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                unsafe.append(path.relative_to(root).as_posix())
            elif path.is_file():
                files.append(path)
    add(
        "submission-files",
        not unsafe,
        "all submission entries are regular files/directories",
        "unsafe submission entries: " + ", ".join(unsafe[:10]),
    )
    entrypoint = root / "index.html"
    if not entrypoint.is_file() or entrypoint.is_symlink():
        add("entrypoint", False, "index.html is present", "index.html is required")
        return CandidateCheckResult(False, tuple(checks))
    source_parts: list[str] = []
    unreadable: list[str] = []
    for path in files:
        if path.suffix.lower() not in {".html", ".htm", ".js", ".mjs", ".css"}:
            continue
        try:
            source_parts.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            unreadable.append(path.relative_to(root).as_posix())
    add("entrypoint", True, "index.html is present and readable", "index.html is required")
    add(
        "source-readable",
        not unreadable,
        "browser source files are UTF-8 readable",
        "unreadable browser source files: " + ", ".join(unreadable[:10]),
    )
    combined = "\n".join(source_parts)
    external = _EXTERNAL_REFERENCE.search(combined)
    add(
        "offline-runtime",
        external is None,
        "no external runtime dependency is referenced",
        "an external network runtime dependency is referenced",
    )
    # This is only a useful source diagnostic. Runtime callback registration is
    # authoritative; valid JavaScript may alias the injected global before use.
    has_gate_reference = bool(re.search(r"\bRalphGates\b", combined))
    add(
        "gates-interface-source",
        has_gate_reference,
        "the submission references the injected RalphGates global",
        "reference RalphGates and register the two gates/v1 arrival callbacks when it is present",
    )
    backend = bool(re.search(r"\b(?:WebSocket|EventSource)\s*\(", combined))
    add("no-backend", not backend, "no backend transport is required", "the artifact requires a backend transport")
    tree_hash: str | None = None
    try:
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
    return CandidateCheckResult(
        not any(item["result"] == "fail" for item in checks),
        tuple(checks),
        tree_hash=tree_hash,
    )


check_candidate = check_static_candidate
validate_candidate = check_static_candidate


@dataclass(frozen=True, slots=True)
class GateThresholds:
    minimum_warmup_completion_ratio: float = 0.75
    minimum_warmup_pedestrian_ratio: float = 0.5
    stage_completion_ratio: float = 0.70
    completion_grace_ms: int = 10_000
    maximum_backlog_fraction: float = 0.60


@dataclass(frozen=True, slots=True)
class AssertionResult:
    assertion_id: str
    severity: str
    result: str
    detail: str
    scenario_id: str
    seed: int
    detector: str = "gates/v1"
    evidence_refs: tuple[str, ...] = ()
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
        return {
            "code": self.code,
            "severity": self.severity,
            "stage_id": self.stage_id,
            "detail": self.detail,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class CapacityStageResult:
    stage_id: str
    offered_cars_per_minute: float
    requested: int
    completed: int
    completion_ratio: float
    observed_throughput_per_minute: float
    outstanding_at_end: int
    max_completion_ms: int | None
    qualifying: bool
    failure_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "offered_cars_per_minute": self.offered_cars_per_minute,
            "requested": self.requested,
            "completed": self.completed,
            "completion_ratio": self.completion_ratio,
            "observed_throughput_per_minute": self.observed_throughput_per_minute,
            "outstanding_at_end": self.outstanding_at_end,
            "max_completion_ms": self.max_completion_ms,
            "qualifying": self.qualifying,
            "failure_codes": list(self.failure_codes),
        }


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    attempted: bool
    passed: bool
    outstanding_at_start: int
    outstanding_at_end: int
    clear_time_ms: int | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "passed": self.passed,
            "outstanding_at_start": self.outstanding_at_start,
            "outstanding_at_end": self.outstanding_at_end,
            "clear_time_ms": self.clear_time_ms,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    challenge: str
    scenario_id: str
    seed: int
    outcome: str
    measurement_status: str
    assertions: tuple[AssertionResult, ...]
    capacity_curve: tuple[CapacityStageResult, ...]
    failures: tuple[FailureRecord, ...]
    recovery: RecoveryResult
    runtime_observations: tuple[dict[str, Any], ...]
    metrics: Mapping[str, Any]
    performance_eligible: bool

    @property
    def passed(self) -> bool:
        return self.outcome == "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "challenge": self.challenge,
            "scenario_id": self.scenario_id,
            "seed": self.seed,
            "outcome": self.outcome,
            "measurement_status": self.measurement_status,
            "assertions": [item.to_dict() for item in self.assertions],
            "capacity_curve": [item.to_dict() for item in self.capacity_curve],
            "failures": [item.to_dict() for item in self.failures],
            "recovery": self.recovery.to_dict(),
            "runtime_observations": [dict(item) for item in self.runtime_observations],
            "metrics": dict(self.metrics),
            "performance_eligible": self.performance_eligible,
        }


def _assertion(
    scenario: GateScenario,
    assertion_id: str,
    passed: bool,
    success: str,
    failure: str,
    *,
    severity: str = "critical",
    threshold: Mapping[str, Any] | None = None,
) -> AssertionResult:
    return AssertionResult(
        assertion_id,
        severity,
        "pass" if passed else "fail",
        success if passed else failure,
        scenario.scenario_id,
        scenario.seed,
        threshold=threshold or {},
    )


def _outstanding_at(observations: Sequence[Mapping[str, Any]], at_ms: int) -> int:
    eligible = [item for item in observations if int(item.get("time_ms", -1)) <= at_ms]
    return int(eligible[-1].get("outstanding_cars", 0)) if eligible else 0


def _capacity_curve(
    scenario: GateScenario,
    completions: Mapping[str, Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
    thresholds: GateThresholds,
) -> tuple[CapacityStageResult, ...]:
    results: list[CapacityStageResult] = []
    for stage in scenario.stages:
        cohort = [item for item in scenario.cars if stage.start_ms <= item.arrival_ms < stage.end_ms]
        grace_end = min(scenario.horizon_ms, stage.end_ms + thresholds.completion_grace_ms)
        completed = [
            completions[item.id]
            for item in cohort
            if item.id in completions and int(completions[item.id].get("completed_ms", scenario.horizon_ms + 1)) <= grace_end
        ]
        ratio = len(completed) / len(cohort) if cohort else 1.0
        completed_during_stage = sum(
            stage.start_ms <= int(item.get("completed_ms", -1)) < stage.end_ms
            for item in completions.values()
            if item.get("kind") == "car"
        )
        throughput = completed_during_stage * 60_000 / stage.duration_ms
        outstanding = _outstanding_at(observations, stage.end_ms)
        issued_to_end = sum(item.arrival_ms < stage.end_ms for item in scenario.cars)
        failures: list[str] = []
        if stage.qualifying and ratio < thresholds.stage_completion_ratio:
            failures.append("completion-ratio")
        backlog_limit = max(2, round(issued_to_end * thresholds.maximum_backlog_fraction))
        if stage.qualifying and outstanding > backlog_limit:
            failures.append("backlog-growth")
        latencies = [int(item.get("latency_ms", 0)) for item in completed]
        results.append(
            CapacityStageResult(
                stage.id,
                stage.offered_cars_per_minute,
                len(cohort),
                len(completed),
                round(ratio, 6),
                round(throughput, 6),
                outstanding,
                max(latencies, default=None),
                stage.qualifying and not failures,
                tuple(failures),
            )
        )
    return tuple(results)


def _recovery(
    scenario: GateScenario,
    observations: Sequence[Mapping[str, Any]],
) -> RecoveryResult:
    cooldown = next((item for item in scenario.stages if item.cooldown), None)
    if cooldown is None:
        return RecoveryResult(False, False, 0, 0, None, "scenario has no cooldown stage")
    start = _outstanding_at(observations, cooldown.start_ms)
    end = _outstanding_at(observations, cooldown.end_ms)
    clear = next(
        (
            int(item.get("time_ms", 0)) - cooldown.start_ms
            for item in observations
            if int(item.get("time_ms", -1)) >= cooldown.start_ms
            and int(item.get("outstanding_cars", 0)) == 0
        ),
        None,
    )
    passed = end == 0 or end <= max(1, round(start * 0.2))
    return RecoveryResult(
        True,
        passed,
        start,
        end,
        clear,
        "outstanding cars cleared or substantially recovered" if passed else "outstanding cars did not recover during cooldown",
    )


def evaluate_gate_monitor(
    scenario: GateScenario,
    monitor: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    *,
    runtime_errors: Sequence[str] = (),
    network_violations: Sequence[str] = (),
    thresholds: GateThresholds | None = None,
) -> EvaluationResult:
    """Derive throughput and readiness solely from evaluator-owned gate evidence."""

    thresholds = thresholds or GateThresholds()
    issued = monitor.get("issued", [])
    raw_completions = monitor.get("completions", [])
    invalid = monitor.get("invalid", [])
    issued = issued if isinstance(issued, list) else []
    raw_completions = raw_completions if isinstance(raw_completions, list) else []
    invalid = invalid if isinstance(invalid, list) else [{"code": "malformed-monitor"}]
    completions = {
        str(item.get("id")): item
        for item in raw_completions
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    expected_arrivals = len(scenario.cars) + len(scenario.pedestrians)
    ready = monitor.get("ready") is True
    warmup = next(stage for stage in scenario.stages if stage.qualifying)
    warmup_cars = [item for item in scenario.cars if warmup.start_ms <= item.arrival_ms < warmup.end_ms]
    warmup_pedestrians = [item for item in scenario.pedestrians if warmup.start_ms <= item.arrival_ms < warmup.end_ms]
    grace_end = min(scenario.horizon_ms, warmup.end_ms + thresholds.completion_grace_ms)
    warmup_car_completed = sum(
        item.id in completions and int(completions[item.id].get("completed_ms", scenario.horizon_ms + 1)) <= grace_end
        for item in warmup_cars
    )
    warmup_ped_completed = sum(
        item.id in completions and int(completions[item.id].get("completed_ms", scenario.horizon_ms + 1)) <= grace_end
        for item in warmup_pedestrians
    )
    car_ratio = warmup_car_completed / len(warmup_cars) if warmup_cars else 1.0
    ped_ratio = warmup_ped_completed / len(warmup_pedestrians) if warmup_pedestrians else 1.0
    base_assertions = (
        _assertion(scenario, "gates-interface-ready", ready, "gates/v1 callbacks registered", "gates/v1 callbacks were not registered"),
        _assertion(scenario, "arrival-delivery", len(issued) == expected_arrivals, f"all {expected_arrivals} arrivals were delivered", f"delivered {len(issued)} of {expected_arrivals} evaluator arrivals"),
        _assertion(scenario, "completion-integrity", not invalid, "completion IDs and finish gates are valid", f"{len(invalid)} invalid completion notification(s) were observed"),
        _assertion(scenario, "browser-runtime-stability", not runtime_errors, "browser produced no runtime errors", f"browser produced {len(runtime_errors)} runtime error(s)"),
        _assertion(scenario, "offline-runtime", not network_violations, "browser made no blocked network requests", f"browser attempted {len(network_violations)} blocked network request(s)"),
        _assertion(
            scenario,
            "warmup-car-service",
            car_ratio >= thresholds.minimum_warmup_completion_ratio,
            f"warmup completed {warmup_car_completed}/{len(warmup_cars)} cars",
            f"warmup completed only {warmup_car_completed}/{len(warmup_cars)} cars",
            threshold={"minimum_completion_ratio": thresholds.minimum_warmup_completion_ratio},
        ),
        _assertion(
            scenario,
            "warmup-pedestrian-service",
            ped_ratio >= thresholds.minimum_warmup_pedestrian_ratio,
            f"warmup completed {warmup_ped_completed}/{len(warmup_pedestrians)} pedestrians",
            f"warmup completed only {warmup_ped_completed}/{len(warmup_pedestrians)} pedestrians",
            threshold={"minimum_completion_ratio": thresholds.minimum_warmup_pedestrian_ratio},
        ),
    )
    capacity = _capacity_curve(scenario, completions, observations, thresholds)
    recovery = _recovery(scenario, observations)
    capacity_assertions = tuple(
        _assertion(
            scenario,
            f"capacity-stage-{stage.stage_id}",
            not stage.failure_codes,
            f"{stage.stage_id} sustained its offered load",
            f"{stage.stage_id} failed: {', '.join(stage.failure_codes)}",
            severity="major",
            threshold={
                "stage_completion_ratio": thresholds.stage_completion_ratio,
                "maximum_backlog_fraction": thresholds.maximum_backlog_fraction,
            },
        )
        for stage in capacity
        if stage.qualifying or stage.failure_codes
    )
    recovery_assertions = (
        _assertion(
            scenario,
            "cooldown-recovery",
            recovery.passed,
            recovery.detail,
            recovery.detail,
            severity="major",
        ),
    ) if recovery.attempted else ()
    assertions = base_assertions + capacity_assertions + recovery_assertions
    # Functional eligibility is evaluated before capacity and recovery. A
    # runnable, correctly wired artifact may still be measured at the load it
    # can sustain, even when it fails a held stage or cooldown requirement.
    functional_failures = tuple(
        item for item in base_assertions if item.result == "fail"
    )
    performance_eligible = (
        not functional_failures
        and ready
        and len(issued) == expected_arrivals
    )
    failures = tuple(
        FailureRecord(item.assertion_id, item.severity, None, item.detail)
        for item in assertions
        if item.result == "fail"
    )
    failures += tuple(
        FailureRecord(
            f"capacity:{stage.stage_id}:{code}",
            "major",
            stage.stage_id,
            f"{stage.stage_id} failed {code}",
        )
        for stage in capacity
        for code in stage.failure_codes
    )
    if recovery.attempted and not recovery.passed:
        failures += (
            FailureRecord(
                "cooldown-recovery",
                "major",
                "cooldown",
                recovery.detail,
            ),
        )
    car_completions = [item for item in raw_completions if isinstance(item, Mapping) and item.get("kind") == "car"]
    pedestrian_completions = [item for item in raw_completions if isinstance(item, Mapping) and item.get("kind") == "pedestrian"]
    latencies = sorted(int(item.get("latency_ms", 0)) for item in car_completions)
    qualifying = [item for item in capacity if item.qualifying]
    outcome = "passed" if not failures else "failed"
    measurement_status = "measured" if ready and len(issued) == expected_arrivals else "unmeasurable"
    metrics = {
        "measurement_status": measurement_status,
        "performance_eligible": performance_eligible,
        "issued_cars": len(scenario.cars),
        "completed_cars": len(car_completions),
        "outstanding_cars": max(0, len(scenario.cars) - len(car_completions)),
        "issued_pedestrians": len(scenario.pedestrians),
        "completed_pedestrians": len(pedestrian_completions),
        "outstanding_pedestrians": max(0, len(scenario.pedestrians) - len(pedestrian_completions)),
        "invalid_completions": len(invalid),
        "median_car_completion_ms": median(latencies) if latencies else None,
        "maximum_car_completion_ms": max(latencies, default=None),
        "peak_monitored_throughput": max(
            (item.observed_throughput_per_minute for item in qualifying),
            default=0,
        ),
        "last_qualifying_stage": qualifying[-1].stage_id if qualifying else None,
        "first_failure_stage": next((item.stage_id for item in capacity if item.failure_codes), None),
        "monitor_observation_count": len(observations),
    }
    return EvaluationResult(
        "busy-intersection/v1",
        scenario.scenario_id,
        scenario.seed,
        outcome,
        measurement_status,
        assertions,
        capacity,
        failures,
        recovery,
        tuple(dict(item) for item in observations),
        metrics,
        performance_eligible,
    )


__all__ = [
    "AssertionResult",
    "CandidateCheckResult",
    "CapacityStageResult",
    "EvaluationResult",
    "FailureRecord",
    "GateThresholds",
    "RecoveryResult",
    "check_candidate",
    "check_static_candidate",
    "evaluate_gate_monitor",
    "validate_candidate",
]
