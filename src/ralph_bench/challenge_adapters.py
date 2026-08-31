"""Challenge execution boundary.

The conductor coordinates a challenge run but does not know its public-pack
layout, scenario type, evaluator protocol, or repair vocabulary. Each
challenge adapter owns those details behind this small boundary. A future city
can therefore use a different topology and protocol without adding branches to
the run lifecycle.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Protocol, TYPE_CHECKING

from .browser_runtime import BrowserEvaluationArtifacts, run_browser_evaluation
from .conformance import load_public_smoke_scenario
from .execution import PublicCheckResult
from .gate_evaluator import CandidateCheckResult, check_static_candidate
from .gates import GateScenario, balanced_seed_for_repetition, build_balanced_gate_scenario

if TYPE_CHECKING:
    from .conductor import ProgressReporter


class ChallengeAdapterError(ValueError):
    """A challenge cannot prepare or execute its requested run."""


@dataclass(frozen=True, slots=True)
class ChallengeRun:
    """Challenge-owned materialization used by the generic conductor."""

    challenge_id: str
    scenario_pack: str
    seed: int
    scenario: object
    scenario_id: str
    scenario_profile: str
    scenario_document: Mapping[str, Any]
    challenge_document: Mapping[str, Any]
    public_source: Path


class ChallengeAdapter(Protocol):
    challenge_id: str

    def seed_for_repetition(self, repetition: int) -> int: ...

    def prepare(
        self, project_root: Path, scenario_pack: str, seed: int
    ) -> ChallengeRun: ...

    def public_check(
        self, path: Path, reporter: "ProgressReporter", *, label: str
    ) -> PublicCheckResult: ...

    def evaluate(
        self,
        challenge_run: ChallengeRun,
        candidate: Path,
        output: Path,
        *,
        raw_evidence: Path,
        timeout_seconds: float,
        chromium: Path,
        playwright_browsers_path: Path,
    ) -> BrowserEvaluationArtifacts: ...

    def public_conformance(
        self,
        project_root: Path,
        candidate: Path,
        output: Path,
        *,
        raw_evidence: Path,
        timeout_seconds: float,
        chromium: Path,
        playwright_browsers_path: Path,
    ) -> Mapping[str, Any]: ...

    def repair_check(
        self,
        static: PublicCheckResult,
        evaluation: Mapping[str, Any],
        reporter: "ProgressReporter",
        *,
        label: str,
        public_evaluation: Mapping[str, Any] | None = None,
    ) -> PublicCheckResult: ...

    def prompt_builder(
        self,
        base_prompt: str,
        *,
        client: str,
        workspace: Path,
        public_challenge: Path,
    ) -> tuple[
        Callable[[int, Mapping[str, Any] | None], str],
        dict[int, str],
        dict[int, Mapping[str, Any] | None],
    ]: ...


class ChallengeRegistry:
    """Explicit challenge registry, parallel to the adapter-family registry."""

    def __init__(self, adapters: Mapping[str, ChallengeAdapter]) -> None:
        self.adapters = dict(adapters)
        for key, adapter in self.adapters.items():
            if key != adapter.challenge_id:
                raise ValueError(f"invalid challenge adapter registration: {key}")

    def get(self, challenge_id: str) -> ChallengeAdapter:
        try:
            return self.adapters[challenge_id]
        except KeyError as exc:
            raise ChallengeAdapterError(
                f"unknown challenge adapter: {challenge_id}"
            ) from exc


def _browser_repair_detail(assertion_id: str) -> str:
    details = {
        "gates-interface-ready": (
            "Keep the gates/v1 registration active and register both arrival "
            "callbacks with the evaluator's object-shaped arguments."
        ),
        "arrival-delivery": (
            "Accept every evaluator-issued car and pedestrian promptly and "
            "create a corresponding visible traveler."
        ),
        "completion-integrity": (
            "Finish each evaluator traveler exactly once, using the requested "
            "car exit, only after it visibly reaches that finish."
        ),
        "browser-runtime-stability": (
            "Fix startup, console, and page runtime errors while keeping the "
            "animation loop running."
        ),
        "offline-runtime": "Remove network dependencies; the artifact must run offline.",
        "warmup-car-service": (
            "Make evaluator-issued cars move continuously from their requested "
            "entrances to their requested exits and notify Ralph at visible finish."
        ),
        "warmup-pedestrian-service": (
            "Make evaluator-issued pedestrians move across their requested "
            "crossings and notify Ralph at visible finish."
        ),
        "cooldown-recovery": (
            "Let outstanding evaluator-issued cars clear during cooldown while "
            "keeping the simulation responsive."
        ),
    }
    if assertion_id.startswith("capacity-stage-"):
        return (
            "Keep the simulation responsive and service evaluator-issued cars "
            "through this offered-load stage without unbounded backlog."
        )
    return details.get(
        assertion_id,
        "Repair the evaluator-visible traveler behavior while preserving the "
        "offline runtime and continuous animation.",
    )


class BusyIntersectionChallengeAdapter:
    """The P0-A gates/v1 challenge implementation."""

    challenge_id = "busy-intersection/v1"
    scenario_pack = "traffic-intersection-p0a"

    def __init__(
        self,
        *,
        browser_evaluator: Callable[..., BrowserEvaluationArtifacts] = run_browser_evaluation,
    ) -> None:
        self._browser_evaluator = browser_evaluator

    def seed_for_repetition(self, repetition: int) -> int:
        return balanced_seed_for_repetition(repetition)

    def prepare(
        self, project_root: Path, scenario_pack: str, seed: int
    ) -> ChallengeRun:
        if scenario_pack != self.scenario_pack:
            raise ChallengeAdapterError(
                f"unsupported scenario pack for {self.challenge_id}: {scenario_pack!r}"
            )
        public_source = (
            Path(project_root) / "challenges" / "busy-intersection" / "v1" / "public"
        )
        if not public_source.is_dir():
            raise ChallengeAdapterError(
                f"Busy Intersection public pack is missing: {public_source}"
            )
        try:
            challenge_document = json.loads(
                (public_source / "challenge.json").read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ChallengeAdapterError("Busy Intersection challenge pack is unreadable") from exc
        if not isinstance(challenge_document, dict):
            raise ChallengeAdapterError("Busy Intersection challenge document must be an object")
        scenario = build_balanced_gate_scenario(seed)
        challenge_document = {
            **challenge_document,
            "scenario_pack": scenario_pack,
            "scenario": scenario.to_dict(),
            "seed": seed,
        }
        return ChallengeRun(
            self.challenge_id,
            scenario_pack,
            seed,
            scenario,
            scenario.scenario_id,
            scenario.profile,
            scenario.to_dict(),
            challenge_document,
            public_source,
        )

    def public_check(
        self, path: Path, reporter: "ProgressReporter", *, label: str
    ) -> PublicCheckResult:
        result: CandidateCheckResult = check_static_candidate(path)
        reporter.emit(
            f"{label}: public artifact checks "
            + ("passed" if result.passed else "failed")
        )
        failed = [item for item in result.checks if item["result"] == "fail"]
        feedback = {
            "summary": (
                "All public artifact checks passed."
                if not failed
                else "Repair every failed public artifact check."
            ),
            "checks": [dict(item) for item in result.checks],
        }
        return PublicCheckResult(
            result.passed,
            feedback,
            tuple(str(item["id"]) for item in result.checks),
        )

    def evaluate(
        self,
        challenge_run: ChallengeRun,
        candidate: Path,
        output: Path,
        *,
        raw_evidence: Path,
        timeout_seconds: float,
        chromium: Path,
        playwright_browsers_path: Path,
    ) -> BrowserEvaluationArtifacts:
        if not isinstance(challenge_run.scenario, GateScenario):
            raise ChallengeAdapterError("Busy Intersection run has an invalid scenario")
        return self._browser_evaluator(
            candidate,
            output,
            raw_evidence=raw_evidence,
            timeout_seconds=timeout_seconds,
            seed=challenge_run.seed,
            chromium=chromium,
            playwright_browsers_path=playwright_browsers_path,
            scenario=challenge_run.scenario,
            evaluation_mode="gates",
        )

    def public_conformance(
        self,
        project_root: Path,
        candidate: Path,
        output: Path,
        *,
        raw_evidence: Path,
        timeout_seconds: float,
        chromium: Path,
        playwright_browsers_path: Path,
    ) -> Mapping[str, Any]:
        scenario = load_public_smoke_scenario(
            Path(project_root)
            / "challenges"
            / "busy-intersection"
            / "v1"
            / "public"
            / "scenario-pack.json"
        )
        artifacts = self._browser_evaluator(
            candidate,
            output,
            raw_evidence=raw_evidence,
            timeout_seconds=timeout_seconds,
            seed=scenario.seed,
            chromium=chromium,
            playwright_browsers_path=playwright_browsers_path,
            scenario=scenario,
            evaluation_mode="conformance",
        )
        if not isinstance(artifacts.result, Mapping):
            raise ChallengeAdapterError("public conformance returned malformed evidence")
        if not isinstance(artifacts.result.get("evaluation"), Mapping):
            raise ChallengeAdapterError("public conformance omitted evaluation evidence")
        return dict(artifacts.result)

    def repair_check(
        self,
        static: PublicCheckResult,
        evaluation: Mapping[str, Any],
        reporter: "ProgressReporter",
        *,
        label: str,
        public_evaluation: Mapping[str, Any] | None = None,
    ) -> PublicCheckResult:
        assertion_sources = (public_evaluation, evaluation)
        failed_assertions: list[dict[str, Any]] = []
        assertion_ids: list[str] = list(static.assertion_ids)
        seen_failures: set[str] = set()
        for source in assertion_sources:
            assertions = source.get("assertions", []) if isinstance(source, Mapping) else []
            if not isinstance(assertions, list):
                continue
            for assertion in assertions:
                if not isinstance(assertion, Mapping):
                    continue
                assertion_id = assertion.get("assertion_id")
                if not isinstance(assertion_id, str) or not assertion_id.strip():
                    continue
                if assertion_id not in assertion_ids:
                    assertion_ids.append(assertion_id)
                if assertion.get("result") == "fail" and assertion_id not in seen_failures:
                    seen_failures.add(assertion_id)
                    failed_assertions.append(
                        {
                            "id": assertion_id,
                            "result": "fail",
                            "detail": _browser_repair_detail(assertion_id),
                        }
                    )
        passed = (
            static.passed
            and evaluation.get("outcome") == "passed"
            and (
                public_evaluation is None
                or public_evaluation.get("outcome") == "passed"
            )
        )
        reporter.emit(
            f"{label}: browser artifact checks "
            + ("passed" if passed else "failed")
        )
        checks = [dict(item) for item in static.feedback.get("checks", [])]
        checks.extend(failed_assertions)
        if not checks:
            checks.append(
                {
                    "id": "browser-evaluation",
                    "result": "fail",
                    "detail": _browser_repair_detail("browser-evaluation"),
                }
            )
        feedback = {
            "summary": (
                "The artifact passed static and browser checks."
                if passed
                else "Repair the existing artifact using these bounded evaluator checks."
            ),
            "checks": checks,
        }
        return PublicCheckResult(passed, feedback, tuple(assertion_ids))

    def prompt_builder(
        self,
        base_prompt: str,
        *,
        client: str,
        workspace: Path,
        public_challenge: Path,
    ) -> tuple[
        Callable[[int, Mapping[str, Any] | None], str],
        dict[int, str],
        dict[int, Mapping[str, Any] | None],
    ]:
        prompts: dict[int, str] = {}
        feedbacks: dict[int, Mapping[str, Any] | None] = {}

        def build(attempt: int, feedback: Mapping[str, Any] | None) -> str:
            if client in {"pi", "harness/pi"}:
                text = (
                    "Use the write tool exactly once now to create index.html, then "
                    "stop. Do not explain or plan. Keep it under 3,500 characters: "
                    "standalone offline canvas animation showing a simple four-way "
                    "intersection, moving cars, and pedestrians. When "
                    "window.RalphGates exists, register carArrived({id,entersFrom,"
                    "exitsTo}) and pedestrianArrived({id,crossing,direction}); move "
                    "each received traveler across the canvas and call the matching "
                    "finish method exactly once when it leaves. Always animate. No "
                    "network, comments, libraries, or HUD.\n"
                )
            else:
                text = (
                    base_prompt.rstrip()
                    + f"\n\nWork only in {workspace}. Public challenge files are available "
                    f"read-only at {public_challenge}. Put the complete final static "
                    f"submission directly in {workspace}, including index.html.\n"
                )
            if feedback is not None:
                text += (
                    "\nThis is the single evaluator-controlled repair pass. Open the "
                    "existing index.html, fix it in place using the evaluator "
                    "feedback below, and do not replace the task with a different "
                    "artifact:\n"
                    + json.dumps(dict(feedback), ensure_ascii=False, sort_keys=True, indent=2)
                    + "\n"
                )
            prompts[attempt] = text
            feedbacks[attempt] = None if feedback is None else dict(feedback)
            return text

        return build, prompts, feedbacks


def built_in_challenge_registry(
    *,
    browser_evaluator: Callable[..., BrowserEvaluationArtifacts] = run_browser_evaluation,
) -> ChallengeRegistry:
    return ChallengeRegistry(
        {
            BusyIntersectionChallengeAdapter.challenge_id: BusyIntersectionChallengeAdapter(
                browser_evaluator=browser_evaluator
            )
        }
    )


__all__ = [
    "BusyIntersectionChallengeAdapter",
    "ChallengeAdapter",
    "ChallengeAdapterError",
    "ChallengeRegistry",
    "ChallengeRun",
    "built_in_challenge_registry",
]
