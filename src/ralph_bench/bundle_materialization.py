"""Build the concrete P0-A bundle tree from conductor-owned evidence.

The ZIP writer in :mod:`ralph_bench.bundles` deliberately accepts only an
already-complete directory.  This module owns the complementary operation: it
maps typed run evidence into that directory, copies only regular files, and
then hands the result to the independently validating finalizer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import stat
from typing import Any

from .bundles import FinalizedBundle, finalize_bundle
from .costs import CostEvidence


class BundleMaterializationError(ValueError):
    """Run evidence cannot be represented safely by the P0-A profile."""


def _json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BundleMaterializationError("bundle JSON must be finite data") from exc


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError as exc:
        raise BundleMaterializationError(f"bundle path already exists: {path}") from exc


def _copy_new(source: Path, destination: Path) -> None:
    try:
        mode = source.lstat().st_mode
    except OSError as exc:
        raise BundleMaterializationError(f"bundle source is missing: {source}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise BundleMaterializationError(
            f"bundle source must be a regular file: {source}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as reader, destination.open("xb") as writer:
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
    except FileExistsError as exc:
        raise BundleMaterializationError(
            f"bundle path already exists: {destination}"
        ) from exc


def _copy_tree(source: Path, destination: Path) -> int:
    if not source.is_dir() or source.is_symlink():
        raise BundleMaterializationError(
            f"bundle tree source must be a real directory: {source}"
        )
    copied = 0
    for root, directories, files in os.walk(source, followlinks=False):
        root_path = Path(root)
        for name in directories:
            directory = root_path / name
            if directory.is_symlink():
                raise BundleMaterializationError(
                    f"bundle tree contains a symlink: {directory}"
                )
        for name in files:
            path = root_path / name
            relative = path.relative_to(source)
            _copy_new(path, destination / relative)
            copied += 1
    return copied


@dataclass(frozen=True, slots=True)
class AttemptBundleEvidence:
    attempt_number: int
    manifest: Mapping[str, Any]
    prompt: str
    public_checks: Mapping[str, Any]
    feedback: Mapping[str, Any] | None = None
    candidate: Path | None = None

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise BundleMaterializationError("attempt number must be positive")
        if not self.prompt.strip():
            raise BundleMaterializationError("attempt prompt is required")


@dataclass(frozen=True, slots=True)
class RunBundleEvidence:
    run_manifest: Mapping[str, Any]
    experiment: Mapping[str, Any]
    challenge: Mapping[str, Any]
    prompt: str
    metrics: Mapping[str, Any]
    cost: CostEvidence
    failures: Sequence[Mapping[str, Any]]
    canonical_events_jsonl: str
    assertions: Mapping[str, Any] | Sequence[Mapping[str, Any]]
    capacity_curve: Mapping[str, Any] | Sequence[Mapping[str, Any]]
    runtime_observations: Mapping[str, Any]
    overview_video: Path
    overview_poster: Path
    overview_metadata: Mapping[str, Any]
    artifact: Path
    raw_evidence: Path
    attempts: Sequence[AttemptBundleEvidence]
    provenance: Mapping[str, Mapping[str, Any]]
    dependencies: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise BundleMaterializationError("run prompt is required")
        if not self.canonical_events_jsonl.strip():
            raise BundleMaterializationError("canonical event evidence is required")
        numbers = [attempt.attempt_number for attempt in self.attempts]
        if not numbers or len(numbers) != len(set(numbers)):
            raise BundleMaterializationError(
                "at least one uniquely numbered attempt is required"
            )


_REQUIRED_PROVENANCE = frozenset(
    {"environment", "redaction", "configuration", "sut-resolution", "isolation"}
)


def materialize_bundle_tree(evidence: RunBundleEvidence, staging: Path) -> Path:
    """Create, but do not finalize, one complete P0-A bundle tree."""

    staging = Path(staging)
    if staging.exists():
        raise BundleMaterializationError(f"bundle staging already exists: {staging}")
    missing = sorted(_REQUIRED_PROVENANCE - set(evidence.provenance))
    if missing:
        raise BundleMaterializationError(
            "missing bundle provenance: " + ", ".join(missing)
        )
    staging.mkdir(parents=True)
    try:
        json_files: dict[str, object] = {
            "run.json": evidence.run_manifest,
            "experiment.json": evidence.experiment,
            "challenge.json": evidence.challenge,
            "metrics.json": evidence.metrics,
            "cost.json": evidence.cost.as_dict(),
            "failures.json": list(evidence.failures),
            "evaluation/assertions.json": evidence.assertions,
            "evaluation/capacity-curve.json": evidence.capacity_curve,
            "evaluation/runtime-observations.json": evidence.runtime_observations,
            "captures/overview.json": evidence.overview_metadata,
            "artifact/dependencies.json": evidence.dependencies,
        }
        for name, value in json_files.items():
            _write_new(staging / name, _json_bytes(value))
        _write_new(staging / "prompt.txt", evidence.prompt.encode("utf-8"))
        _write_new(
            staging / "events/canonical.jsonl",
            evidence.canonical_events_jsonl.encode("utf-8"),
        )

        if _copy_tree(evidence.raw_evidence, staging / "events/raw") < 1:
            raise BundleMaterializationError("raw event evidence is empty")
        if _copy_tree(evidence.artifact, staging / "artifact/submission") < 1:
            # Empty submissions are still evidence.  The marker is explicitly
            # conductor-authored and does not pretend to be candidate output.
            _write_new(
                staging / "artifact/submission/.ralph-empty-submission",
                b"candidate submission contained no files\n",
            )
        _copy_new(evidence.overview_video, staging / "captures/overview.webm")
        _copy_new(evidence.overview_poster, staging / "captures/overview.png")

        for attempt in sorted(evidence.attempts, key=lambda item: item.attempt_number):
            root = staging / "attempts" / f"attempt-{attempt.attempt_number:03d}"
            _write_new(root / "attempt.json", _json_bytes(attempt.manifest))
            _write_new(root / "prompt.txt", attempt.prompt.encode("utf-8"))
            _write_new(root / "public-checks.json", _json_bytes(attempt.public_checks))
            if attempt.feedback is not None:
                _write_new(root / "feedback.json", _json_bytes(attempt.feedback))
            if attempt.candidate is not None:
                _copy_tree(attempt.candidate, root / "submission")

        for name, value in sorted(evidence.provenance.items()):
            if not name or "/" in name or "\\" in name:
                raise BundleMaterializationError(
                    f"unsafe provenance document name: {name!r}"
                )
            _write_new(staging / "provenance" / f"{name}.json", _json_bytes(value))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return staging


def finalize_run_bundle(
    evidence: RunBundleEvidence,
    *,
    staging: Path,
    output: Path,
) -> FinalizedBundle:
    """Materialize and independently validate/install one immutable bundle."""

    materialize_bundle_tree(evidence, staging)
    return finalize_bundle(staging, output)


__all__ = [
    "AttemptBundleEvidence",
    "BundleMaterializationError",
    "RunBundleEvidence",
    "finalize_run_bundle",
    "materialize_bundle_tree",
]
