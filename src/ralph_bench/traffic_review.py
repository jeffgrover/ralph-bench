"""Resolve external traffic-validity reviews without changing run bundles.

The evaluator can prove that the ``gates/v1`` interface ran and can derive
diagnostic load measurements.  It cannot infer physical traffic validity from
those facts.  A review is therefore a small, immutable sidecar input to the
reporter, tied to both the run ID and selected artifact tree hash.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


TRAFFIC_REVIEW_SCHEMA = "traffic-review/v1"
TRAFFIC_REVIEW_STATUSES = frozenset({"pending", "pass", "fail", "unverifiable"})
REVIEW_RUBRIC = "traffic-human/v1"
REQUIRED_RULES = (
    "collision-avoidance", "signal-compliance", "lane-discipline",
    "physical-scale", "trip-integrity",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ReviewDiagnostic:
    code: str
    path: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class ReviewDocument:
    path: str
    value: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TrafficReview:
    status: str
    run_id: str
    artifact_hash: str
    source: str
    reason: str
    evidence_refs: tuple[str, ...] = ()
    reviewed_intervals: tuple[str, ...] = ()
    reviewer: str | None = None
    rubric_version: str | None = None
    diagnostics: tuple[ReviewDiagnostic, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def performance_comparison_eligible(self) -> bool:
        return self.status == "pass" and not self.diagnostics

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "traffic-review/v2" if self.details else TRAFFIC_REVIEW_SCHEMA,
            "status": self.status,
            "run_id": self.run_id,
            "artifact_hash": self.artifact_hash,
            "source": self.source,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "reviewed_intervals": list(self.reviewed_intervals),
            "reviewer": self.reviewer,
            "rubric_version": self.rubric_version,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            **dict(self.details),
        }


def load_review_documents(directory: Path | None) -> tuple[tuple[ReviewDocument, ...], tuple[ReviewDiagnostic, ...]]:
    """Read review JSON sidecars read-only, quarantining malformed inputs."""

    if directory is None:
        return (), ()
    directory = Path(directory)
    if not directory.exists():
        return (), ()
    if directory.is_symlink() or not directory.is_dir():
        return (), (ReviewDiagnostic("review_directory_invalid", str(directory), "expected a real directory"),)
    documents: list[ReviewDocument] = []
    diagnostics: list[ReviewDiagnostic] = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
        if path.is_symlink() or not path.is_file():
            diagnostics.append(ReviewDiagnostic("review_not_regular_file", path.name))
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            diagnostics.append(ReviewDiagnostic("review_unreadable", path.name, str(exc)))
            continue
        if not isinstance(value, Mapping):
            diagnostics.append(ReviewDiagnostic("review_not_object", path.name))
            continue
        documents.append(ReviewDocument(path.name, value))
    return tuple(documents), tuple(diagnostics)


def _strings(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        return None
    return tuple(item.strip() for item in value)


def _baseline(run: Mapping[str, Any]) -> TrafficReview:
    run_id = str(run.get("run_id", "unknown"))
    artifact_hash = str(run.get("selected_candidate_hash", ""))
    candidate = run.get("traffic_review")
    reason = "no external traffic review supplied"
    if isinstance(candidate, Mapping):
        candidate_status = candidate.get("status")
        if candidate_status == "pending":
            reason = str(candidate.get("reason") or reason)
    return TrafficReview(
        "pending",
        run_id,
        artifact_hash,
        "bundle baseline",
        reason,
    )


def _invalid(
    run_id: str,
    artifact_hash: str,
    source: str,
    reason: str,
    diagnostics: Sequence[ReviewDiagnostic],
    *,
    evidence_refs: Sequence[str] = (),
    reviewed_intervals: Sequence[str] = (),
    reviewer: str | None = None,
    rubric_version: str | None = None,
) -> TrafficReview:
    return TrafficReview(
        "unverifiable",
        run_id,
        artifact_hash,
        source,
        reason,
        tuple(evidence_refs),
        tuple(reviewed_intervals),
        reviewer,
        rubric_version,
        tuple(diagnostics),
    )


def _resolve_document(
    document: ReviewDocument,
    expected_run_id: str,
    expected_artifact_hash: str,
    run: Mapping[str, Any],
) -> TrafficReview | None:
    value = document.value
    if value.get("run_id") != expected_run_id:
        return None
    diagnostics: list[ReviewDiagnostic] = []
    schema = value.get("schema_version")
    if not isinstance(schema, str) or schema not in {TRAFFIC_REVIEW_SCHEMA, "traffic-review/v2"}:
        diagnostics.append(ReviewDiagnostic("review_schema_unknown", document.path, str(schema)))
    artifact_hash = value.get("artifact_hash")
    if not isinstance(artifact_hash, str) or _SHA256.fullmatch(artifact_hash) is None:
        diagnostics.append(ReviewDiagnostic("review_artifact_hash_invalid", document.path))
    elif artifact_hash != expected_artifact_hash:
        diagnostics.append(ReviewDiagnostic("review_artifact_mismatch", document.path, "selected artifact hash differs"))
    status = value.get("status")
    if not isinstance(status, str) or status not in TRAFFIC_REVIEW_STATUSES:
        diagnostics.append(ReviewDiagnostic("review_status_invalid", document.path, str(status)))
        status = "unverifiable"
    evidence_refs = _strings(value.get("evidence_refs", []))
    if evidence_refs is None:
        diagnostics.append(ReviewDiagnostic("review_evidence_refs_invalid", document.path))
        evidence_refs = ()
    intervals = _strings(value.get("reviewed_intervals", []))
    if intervals is None:
        diagnostics.append(ReviewDiagnostic("review_intervals_invalid", document.path))
        intervals = ()
    reviewer = value.get("reviewer")
    rubric_version = value.get("rubric_version")
    if status != "pending":
        if not isinstance(reviewer, str) or not reviewer.strip():
            diagnostics.append(ReviewDiagnostic("reviewer_missing", document.path))
        if not isinstance(rubric_version, str) or not rubric_version.strip():
            diagnostics.append(ReviewDiagnostic("rubric_version_missing", document.path))
        if not evidence_refs:
            diagnostics.append(ReviewDiagnostic("review_evidence_missing", document.path))
        if not intervals:
            diagnostics.append(ReviewDiagnostic("review_intervals_missing", document.path))
    findings = value.get("findings")
    # A demonstrated violation takes precedence even if other rules are unreviewed.
    if isinstance(findings, Mapping) and any(
        isinstance(item, Mapping) and item.get("status") == "fail"
        for item in findings.values()
    ):
        status = "fail"
    coverage_complete = value.get("coverage_complete")
    if status == "pass" and (coverage_complete is not True or not intervals):
        diagnostics.append(
            ReviewDiagnostic(
                "review_coverage_insufficient",
                document.path,
                "a pass requires coverage_complete=true and reviewed_intervals",
            )
        )
    if status == "pass":
        if schema != "traffic-review/v2" or rubric_version != REVIEW_RUBRIC:
            diagnostics.append(ReviewDiagnostic("review_rubric_unsupported", document.path))
        if (
            not isinstance(run.get("scenario_id"), str)
            or value.get("scenario_id") != run.get("scenario_id")
            or type(value.get("seed")) is not int
            or value.get("seed") != run.get("seed")
        ):
            diagnostics.append(ReviewDiagnostic("review_scenario_mismatch", document.path))
        if not isinstance(findings, Mapping) or set(findings) != set(REQUIRED_RULES):
            diagnostics.append(ReviewDiagnostic("review_rules_incomplete", document.path))
        else:
            for rule, finding in findings.items():
                if not isinstance(finding, Mapping):
                    diagnostics.append(ReviewDiagnostic("review_finding_invalid", document.path, rule))
                    continue
                refs = _strings(finding.get("evidence_refs"))
                if (
                    finding.get("status") != "pass"
                    or not isinstance(finding.get("detail"), str)
                    or not finding["detail"].strip()
                    or not refs
                    or not set(refs).issubset(evidence_refs)
                    or not any(ref.split("#", 1)[0] == "captures/overview.webm" for ref in refs)
                ):
                    diagnostics.append(ReviewDiagnostic("review_finding_insufficient", document.path, rule))
        coverage = value.get("coverage_ms")
        if (
            not isinstance(coverage, list) or not coverage
            or any(
                not isinstance(interval, list) or len(interval) != 2
                or any(type(point) is not int for point in interval)
                or interval[0] < 0 or interval[1] <= interval[0]
                for interval in coverage
            )
        ):
            diagnostics.append(ReviewDiagnostic("review_coverage_invalid", document.path))
    if diagnostics:
        return _invalid(
            expected_run_id,
            expected_artifact_hash,
            document.path,
            "review identity or evidence is invalid",
            diagnostics,
            evidence_refs=evidence_refs,
            reviewed_intervals=intervals,
            reviewer=reviewer if isinstance(reviewer, str) else None,
            rubric_version=rubric_version if isinstance(rubric_version, str) else None,
        )
    return TrafficReview(
        str(status),
        expected_run_id,
        expected_artifact_hash,
        document.path,
        str(value.get("reason") or f"traffic review status: {status}"),
        evidence_refs,
        intervals,
        reviewer if isinstance(reviewer, str) else None,
        rubric_version if isinstance(rubric_version, str) else None,
        details={key: value[key] for key in ("scenario_id", "seed", "coverage_ms", "coverage_complete", "findings") if key in value},
    )


def resolve_traffic_review(
    run: Mapping[str, Any],
    documents: Sequence[ReviewDocument] = (),
) -> TrafficReview:
    """Resolve one run to a conservative review state.

    A matching sidecar is the only way to move a run beyond the bundle's
    pending baseline.  A wrong artifact hash or duplicate matching sidecar is
    explicitly ``unverifiable`` rather than silently ignored.
    """

    baseline = _baseline(run)
    matching = [
        review
        for document in documents
        if (review := _resolve_document(document, baseline.run_id, baseline.artifact_hash, run)) is not None
    ]
    if not matching:
        return baseline
    if len(matching) > 1:
        diagnostic = ReviewDiagnostic(
            "review_duplicate_match",
            ", ".join(item.source for item in matching),
            "multiple sidecars match the same run",
        )
        return _invalid(
            baseline.run_id,
            baseline.artifact_hash,
            "reviews",
            "multiple matching reviews are ambiguous",
            (*matching[0].diagnostics, diagnostic),
        )
    return matching[0]


__all__ = [
    "ReviewDiagnostic",
    "ReviewDocument",
    "TRAFFIC_REVIEW_SCHEMA",
    "TRAFFIC_REVIEW_STATUSES",
    "TrafficReview",
    "load_review_documents",
    "resolve_traffic_review",
]
