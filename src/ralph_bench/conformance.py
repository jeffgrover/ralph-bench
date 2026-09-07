"""Agent-runnable public ``gates/v1`` conformance checks.

The public smoke run exercises interface registration, both arrival shapes,
both finish methods, offline browser execution, and visible service. It is an
unscored contract debugger; it does not expose or approximate the private
capacity profile.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping, Sequence

from .browser_runtime import (
    BrowserEvaluationArtifacts,
    find_chromium,
    find_playwright_browsers_path,
    run_browser_evaluation,
)
from .gates import (
    CarArrival,
    DemandStage,
    GateScenario,
    GateSchemaError,
    PedestrianArrival,
)


class ConformanceError(RuntimeError):
    """The public conformance input or execution was invalid."""


PUBLIC_SMOKE_SETTLE_MS = 12_000


def _assertion(
    assertion_id: str,
    passed: bool,
    success: str,
    failure: str,
    *,
    scenario: GateScenario,
) -> dict[str, Any]:
    return {
        "assertion_id": assertion_id,
        "severity": "critical",
        "result": "pass" if passed else "fail",
        "detector": "gates/v1-public-conformance",
        "detail": success if passed else failure,
        "evidence_refs": [],
        "scenario_id": scenario.scenario_id,
        "seed": scenario.seed,
        "threshold": {},
    }


def evaluate_public_conformance(
    scenario: GateScenario,
    monitor: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    *,
    runtime_errors: Sequence[str] = (),
    network_violations: Sequence[str] = (),
) -> dict[str, Any]:
    """Return bounded, non-prescriptive smoke diagnostics for one candidate."""

    issued = monitor.get("issued", [])
    completions = monitor.get("completions", [])
    invalid = monitor.get("invalid", [])
    issued = issued if isinstance(issued, list) else []
    completions = completions if isinstance(completions, list) else []
    invalid = invalid if isinstance(invalid, list) else [{"code": "malformed-monitor"}]
    expected_ids = {item.id for item in (*scenario.cars, *scenario.pedestrians)}
    issued_ids = {
        item.get("id")
        for item in issued
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    completion_ids = {
        item.get("id")
        for item in completions
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    missing_ids = sorted(expected_ids - completion_ids)
    assertions = (
        _assertion(
            "gates-interface-ready",
            monitor.get("ready") is True,
            "gates/v1 callbacks registered",
            "gates/v1 callbacks were not registered",
            scenario=scenario,
        ),
        _assertion(
            "arrival-delivery",
            issued_ids == expected_ids and len(issued) == len(expected_ids),
            f"all {len(expected_ids)} public smoke arrivals were delivered",
            f"delivered {len(issued_ids)} of {len(expected_ids)} public smoke arrivals",
            scenario=scenario,
        ),
        _assertion(
            "completion-integrity",
            not invalid and completion_ids.issubset(expected_ids),
            "completion IDs and finish gates are valid",
            f"{len(invalid)} invalid completion notification(s) were observed",
            scenario=scenario,
        ),
        _assertion(
            "traveler-service",
            completion_ids == expected_ids and len(completions) == len(expected_ids),
            f"all {len(expected_ids)} public smoke travelers finished",
            (
                f"finished {len(completion_ids)} of {len(expected_ids)} public smoke "
                f"travelers; missing {', '.join(missing_ids)}"
            ),
            scenario=scenario,
        ),
        _assertion(
            "browser-runtime-stability",
            not runtime_errors,
            "browser produced no runtime errors",
            f"browser produced {len(runtime_errors)} runtime error(s)",
            scenario=scenario,
        ),
        _assertion(
            "offline-runtime",
            not network_violations,
            "browser made no blocked network requests",
            f"browser attempted {len(network_violations)} blocked network request(s)",
            scenario=scenario,
        ),
    )
    failures = [
        {
            "code": item["assertion_id"],
            "severity": item["severity"],
            "stage_id": None,
            "detail": item["detail"],
            "evidence_refs": [],
        }
        for item in assertions
        if item["result"] == "fail"
    ]
    return {
        "challenge": "busy-intersection/v1",
        "scenario_id": scenario.scenario_id,
        "seed": scenario.seed,
        "outcome": "passed" if not failures else "failed",
        "measurement_status": "smoke",
        "assertions": list(assertions),
        "failures": failures,
        "capacity_curve": [],
        "recovery": {
            "attempted": False,
            "passed": False,
            "outstanding_at_start": 0,
            "outstanding_at_end": 0,
            "clear_time_ms": None,
            "detail": "public conformance does not score capacity or recovery",
        },
        "runtime_observations": [dict(item) for item in observations],
        "metrics": {
            "measurement_status": "smoke",
            "expected_travelers": len(expected_ids),
            "issued_travelers": len(issued_ids),
            "completed_travelers": len(completion_ids),
            "runtime_error_count": len(runtime_errors),
            "network_violation_count": len(network_violations),
            "missing_traveler_ids": missing_ids,
        },
        "performance_eligible": False,
    }


def load_public_smoke_scenario(path: Path) -> GateScenario:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConformanceError(f"public smoke scenario is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise ConformanceError("public smoke scenario must be a JSON object")
    cars = value.get("cars", [])
    pedestrians = value.get("pedestrians", [])
    if not isinstance(cars, list) or not isinstance(pedestrians, list):
        raise ConformanceError("public smoke scenario cars and pedestrians must be lists")
    try:
        if any(not isinstance(item, Mapping) for item in (*cars, *pedestrians)):
            raise GateSchemaError("scenario entries must be objects")
        car_arrivals = tuple(
            CarArrival(
                item["id"],
                item["entersFrom"],
                item["exitsTo"],
                item["at_ms"],
            )
            for item in cars
        )
        pedestrian_arrivals = tuple(
            PedestrianArrival(
                item["id"],
                item["crossing"],
                item["direction"],
                item["at_ms"],
            )
            for item in pedestrians
        )
        max_arrival = max(
            (item.arrival_ms for item in (*car_arrivals, *pedestrian_arrivals)),
            default=0,
        )
        # The smoke pack is deliberately unscored, so allow a modest signal-cycle
        # settle window after the final arrival. Capacity and latency remain private
        # evaluator concerns; this only prevents a valid but slower implementation
        # from failing before it can demonstrate the public finish callbacks.
        horizon = max_arrival + PUBLIC_SMOKE_SETTLE_MS
        return GateScenario(
            "busy-intersection-public-smoke",
            "public-smoke",
            0,
            horizon,
            (DemandStage("public-smoke", 0, horizon, 0, 0, False, False),),
            car_arrivals,
            pedestrian_arrivals,
        )
    except (KeyError, TypeError, ValueError, GateSchemaError) as exc:
        raise ConformanceError("public smoke scenario violates gates/v1 schema") from exc


def run_conformance_evaluation(
    candidate: Path,
    scenario: GateScenario,
    *,
    output: Path,
    raw_evidence: Path,
    timeout_seconds: float = 30.0,
    chromium: Path,
    playwright_browsers_path: Path,
    browser_evaluator: Callable[..., BrowserEvaluationArtifacts] = run_browser_evaluation,
) -> BrowserEvaluationArtifacts:
    """Run one public conformance evaluation using caller-owned directories."""

    candidate = Path(candidate)
    if not candidate.is_dir() or candidate.is_symlink():
        raise ConformanceError("candidate must be a real directory")
    artifacts = browser_evaluator(
        candidate,
        Path(output),
        raw_evidence=Path(raw_evidence),
        timeout_seconds=timeout_seconds,
        seed=scenario.seed,
        chromium=chromium,
        playwright_browsers_path=playwright_browsers_path,
        scenario=scenario,
        evaluation_mode="conformance",
    )
    if not isinstance(artifacts.result, Mapping):
        raise ConformanceError("browser worker returned malformed conformance evidence")
    evaluation = artifacts.result.get("evaluation")
    if not isinstance(evaluation, Mapping):
        raise ConformanceError("browser worker omitted conformance evaluation")
    return artifacts


def run_public_conformance(
    candidate: Path,
    *,
    project_root: Path,
    timeout_seconds: float = 30.0,
    chromium: Path | None = None,
    playwright_browsers_path: Path | None = None,
) -> dict[str, Any]:
    """Run the checked-in unscored smoke scenario without producing a bundle."""

    scenario_path = (
        Path(project_root)
        / "challenges"
        / "busy-intersection"
        / "v1"
        / "public"
        / "scenario-pack.json"
    )
    scenario = load_public_smoke_scenario(scenario_path)
    with tempfile.TemporaryDirectory(prefix="ralph-bench-conformance-") as directory:
        root = Path(directory)
        artifacts = run_conformance_evaluation(
            candidate,
            scenario,
            output=root / "browser-output",
            raw_evidence=root / "raw",
            timeout_seconds=timeout_seconds,
            chromium=chromium or find_chromium(),
            playwright_browsers_path=playwright_browsers_path
            or find_playwright_browsers_path(),
        )
        result = artifacts.result
        evaluation = result.get("evaluation")
        if not isinstance(evaluation, Mapping):
            raise ConformanceError("browser worker omitted conformance evaluation")
        return {
            "schema_version": "conformance/v1",
            "challenge": "busy-intersection/v1",
            "scenario_pack": "traffic-intersection-p0a",
            "scenario_id": scenario.scenario_id,
            "outcome": evaluation.get("outcome"),
            "passed": evaluation.get("outcome") == "passed",
            "assertions": evaluation.get("assertions", []),
            "failures": evaluation.get("failures", []),
            "metrics": evaluation.get("metrics", {}),
            "browser": result.get("browser", {}),
            "monitor": result.get("monitor", {}),
            "capture": result.get("capture", {}),
        }


__all__ = [
    "ConformanceError",
    "evaluate_public_conformance",
    "load_public_smoke_scenario",
    "run_conformance_evaluation",
    "run_public_conformance",
]
