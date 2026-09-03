"""Immutable, validated ``.ralph.zip`` result bundles.

The bundle boundary treats all candidate content as opaque bytes.  It writes
deterministic archives from a prepared directory and validates every archive
before extraction or ingest.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping, Optional, Sequence

from .capture_validation import capture_metadata_issues, media_issues
from .costs import CostEvidence, CostValidationError


CHECKSUMS_NAME = "checksums.sha256"
KNOWN_RUN_SCHEMAS = frozenset({"run/v1"})
KNOWN_REQUIRED_FEATURES: frozenset[str] = frozenset()

# Explicit P0-A profile. Future evidence variants may add files, but cannot
# weaken the path, schema, inventory, or resource checks below.
P0_REQUIRED_FILES = frozenset(
    {
        "run.json", "experiment.json", "challenge.json", "prompt.txt",
        "metrics.json", "cost.json", "failures.json",
        "events/canonical.jsonl", "evaluation/assertions.json",
        "evaluation/capacity-curve.json", "evaluation/runtime-observations.json",
        "captures/overview.webm", "captures/overview.png", "captures/overview.json",
        "provenance/environment.json", "provenance/redaction.json",
        "provenance/configuration.json", "provenance/sut-resolution.json",
        "provenance/isolation.json", "artifact/dependencies.json",
    }
)
_REFERENCE_KEYS = frozenset({
    "evidence", "evidence_ref", "evidence_refs", "evidence_path",
    "evidence_paths", "evidence_file", "evidence_files",
    "evidence_references", "generation_started_evidence", "raw_evidence_refs",
})
_SHA256_LINE = re.compile(r"^(?P<digest>[0-9a-fA-F]{64})[ \t]+(?P<name>\*?[^\s].*)$")


@dataclass(frozen=True, slots=True)
class BundleLimits:
    max_entries: int = 4096
    max_file_size: int = 128 * 1024 * 1024
    max_total_size: int = 512 * 1024 * 1024
    max_compression_ratio: float = 200.0

    def __post_init__(self) -> None:
        if self.max_entries < 1 or self.max_file_size < 0 or self.max_total_size < 0:
            raise ValueError("invalid bundle limits")
        if self.max_compression_ratio <= 0:
            raise ValueError("max_compression_ratio must be positive")


@dataclass(frozen=True, slots=True)
class BundleDiagnostic:
    code: str
    path: Optional[str] = None
    detail: str = ""


@dataclass(frozen=True, slots=True)
class BundleValidationResult:
    valid: bool
    diagnostics: tuple[BundleDiagnostic, ...] = ()
    entries: tuple[str, ...] = ()
    total_size: int = 0
    run_id: Optional[str] = None

    def require_valid(self) -> "BundleValidationResult":
        if not self.valid:
            raise BundleValidationError(self.diagnostics)
        return self


@dataclass(frozen=True, slots=True)
class FinalizedBundle:
    path: Path
    bundle_sha256: str
    entries: tuple[str, ...]

    @property
    def output_path(self) -> Path:
        return self.path

    def __fspath__(self) -> str:
        return os.fspath(self.path)


@dataclass(frozen=True, slots=True)
class ExtractedBundle:
    path: Path
    entries: tuple[str, ...]

    @property
    def output_path(self) -> Path:
        return self.path


class BundleError(ValueError):
    def __init__(self, diagnostics: Sequence[BundleDiagnostic] | BundleDiagnostic):
        if isinstance(diagnostics, BundleDiagnostic):
            diagnostics = (diagnostics,)
        self.diagnostics = tuple(diagnostics)
        super().__init__(", ".join(item.code for item in self.diagnostics) or "bundle_error")


class BundleValidationError(BundleError):
    pass


def _diag(code: str, path: Optional[str] = None, detail: str = "") -> BundleDiagnostic:
    return BundleDiagnostic(code, path, detail)


def _safe_member_name(name: str) -> Optional[BundleDiagnostic]:
    if not name:
        return _diag("empty_or_nul_path", name)
    # Reject rather than normalize backslashes so Windows traversal cannot be
    # smuggled through a POSIX validator.
    if "\\" in name:
        return _diag("unsafe_path", name, "backslashes are not permitted")
    if name.startswith("/") or (len(name) >= 2 and name[1] == ":" and name[0].isalpha()):
        return _diag("unsafe_path", name, "absolute or drive-qualified path")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return _diag("unsafe_path", name, "empty, dot, or parent path component")
    reserved = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
    if name != name.strip():
        return _diag("unsafe_path", name, "leading or trailing whitespace")
    for part in parts:
        if part != part.strip() or part.endswith((".", " ")):
            return _diag("unsafe_path", name, "whitespace or trailing dot/space")
        if ":" in part:
            return _diag("unsafe_path", name, "alternate data stream")
        if part.split(".", 1)[0].casefold() in reserved:
            return _diag("reserved_name", name, part)
        if any(unicodedata.category(char).startswith("C") for char in part):
            return _diag("unsafe_path", name, "control or format character")
    return None


def _member_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _mode_diagnostic(info: zipfile.ZipInfo) -> Optional[BundleDiagnostic]:
    mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    if file_type == stat.S_IFLNK:
        return _diag("symlink_entry", info.filename)
    if file_type not in (0, stat.S_IFREG):
        return _diag("special_file_entry", info.filename)
    if info.is_dir() or (info.external_attr & 0x10 and file_type == 0):
        return _diag("directory_entry", info.filename)
    return None


def _parse_json(path: str, data: bytes, diagnostics: list[BundleDiagnostic]) -> object | None:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        diagnostics.append(_diag("malformed_json", path, str(exc)))
        return None


def _walk_references(value: object, path: str, refs: list[tuple[str, str]]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _REFERENCE_KEYS:
                values = child if isinstance(child, list) else [child]
                refs.extend((path, ref) for ref in values if isinstance(ref, str))
            _walk_references(child, path, refs)
    elif isinstance(value, list):
        for child in value:
            _walk_references(child, path, refs)


def _validate_inventory(raw: bytes, payload_names: set[str], limits: BundleLimits,
                        diagnostics: list[BundleDiagnostic]) -> dict[str, str]:
    if len(raw) > limits.max_file_size:
        diagnostics.append(_diag("file_size_limit", CHECKSUMS_NAME))
        return {}
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        diagnostics.append(_diag("inventory_malformed", CHECKSUMS_NAME, str(exc)))
        return {}
    inventory: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        match = _SHA256_LINE.fullmatch(line)
        if not match:
            diagnostics.append(_diag("inventory_malformed", CHECKSUMS_NAME, f"line {line_number}"))
            continue
        digest = match.group("digest").lower()
        name = match.group("name").removeprefix("*")
        if _safe_member_name(name) is not None or name == CHECKSUMS_NAME:
            diagnostics.append(_diag("inventory_malformed", CHECKSUMS_NAME, name))
            continue
        if name in inventory:
            diagnostics.append(_diag("inventory_duplicate", CHECKSUMS_NAME, name))
        elif _member_key(name) in {_member_key(item) for item in inventory}:
            diagnostics.append(_diag("inventory_case_collision", CHECKSUMS_NAME, name))
        inventory[name] = digest
    for name in sorted(payload_names - set(inventory)):
        diagnostics.append(_diag("inventory_missing_entry", name))
    for name in sorted(set(inventory) - payload_names):
        diagnostics.append(_diag("inventory_unknown_entry", name))
    return inventory


def _profile_diagnostics(names: set[str]) -> list[BundleDiagnostic]:
    diagnostics = [_diag("missing_required_file", name) for name in sorted(P0_REQUIRED_FILES - names)]
    if not any(name.startswith("events/raw/") for name in names):
        diagnostics.append(_diag("missing_raw_evidence", "events/raw/"))
    attempt_manifests = [name for name in names if name.startswith("attempts/") and name.endswith("/attempt.json")]
    if not attempt_manifests:
        diagnostics.append(_diag("missing_attempt_evidence", "attempts/"))
    for manifest in attempt_manifests:
        attempt_dir = manifest.rsplit("/", 1)[0]
        for required in ("prompt.txt", "public-checks.json"):
            if f"{attempt_dir}/{required}" not in names:
                diagnostics.append(_diag("missing_attempt_file", f"{attempt_dir}/{required}"))
    if not any(name.startswith("artifact/submission/") for name in names):
        diagnostics.append(_diag("missing_submission_artifact", "artifact/submission/"))
    return diagnostics


def validate_bundle(bundle_path: os.PathLike[str] | str,
                    limits: BundleLimits | None = None) -> BundleValidationResult:
    """Read-only structural, resource, schema, reference, and checksum validation."""
    limits = limits or BundleLimits()
    path = Path(bundle_path)
    try:
        bundle_mode = path.lstat().st_mode
    except OSError:
        bundle_mode = 0
    if not stat.S_ISREG(bundle_mode):
        return BundleValidationResult(False, (_diag("bundle_not_found", str(path)),))
    try:
        archive = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        return BundleValidationResult(False, (_diag("invalid_zip", str(path), str(exc)),))
    diagnostics: list[BundleDiagnostic] = []
    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_entries:
            diagnostics.append(_diag("entry_limit", str(path)))
        names: set[str] = set()
        folded: dict[str, str] = {}
        info_by_name: dict[str, zipfile.ZipInfo] = {}
        total_size = 0
        for info in infos:
            name = info.filename
            path_diag = _safe_member_name(name)
            if path_diag is not None:
                diagnostics.append(path_diag)
                continue
            if name in names:
                diagnostics.append(_diag("duplicate_entry", name))
                continue
            previous = folded.get(_member_key(name))
            if previous is not None:
                diagnostics.append(_diag("case_collision", name, previous))
                continue
            names.add(name)
            folded[_member_key(name)] = name
            info_by_name[name] = info
            mode_diag = _mode_diagnostic(info)
            if mode_diag is not None:
                diagnostics.append(mode_diag)
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                diagnostics.append(_diag("unsupported_compression", name, str(info.compress_type)))
            if info.file_size > limits.max_file_size:
                diagnostics.append(_diag("file_size_limit", name))
            total_size += max(0, info.file_size)
            if info.file_size > 0 and info.compress_size == 0:
                diagnostics.append(_diag("compression_ratio", name, "zero compressed size"))
            elif info.compress_size and info.file_size / info.compress_size > limits.max_compression_ratio:
                diagnostics.append(_diag("compression_ratio", name))
        if total_size > limits.max_total_size:
            diagnostics.append(_diag("total_size_limit", str(path)))

        if CHECKSUMS_NAME not in names:
            diagnostics.append(_diag("missing_inventory", CHECKSUMS_NAME))
            inventory: dict[str, str] = {}
        else:
            try:
                inventory = _validate_inventory(archive.read(info_by_name[CHECKSUMS_NAME]),
                                                names - {CHECKSUMS_NAME}, limits, diagnostics)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                diagnostics.append(_diag("inventory_read_failed", CHECKSUMS_NAME, str(exc)))
                inventory = {}
        for name in sorted(names - {CHECKSUMS_NAME}):
            info = info_by_name[name]
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                continue
            try:
                digest = hashlib.sha256(archive.read(info)).hexdigest()
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                diagnostics.append(_diag("payload_read_failed", name, str(exc)))
                continue
            if name in inventory and inventory[name] != digest:
                diagnostics.append(_diag("checksum_mismatch", name))

        run_id: Optional[str] = None
        run_manifest: dict[str, object] | None = None
        if "run.json" in info_by_name:
            try:
                manifest = _parse_json("run.json", archive.read(info_by_name["run.json"]), diagnostics)
                if isinstance(manifest, dict):
                    run_manifest = manifest
                    schema = manifest.get("schema_version")
                    if not isinstance(schema, str):
                        diagnostics.append(_diag("run_schema_missing", "run.json"))
                    elif schema not in KNOWN_RUN_SCHEMAS:
                        diagnostics.append(_diag("run_schema_unknown", "run.json", schema))
                    required_features = manifest.get("required_features", [])
                    if not isinstance(required_features, list) or any(
                        not isinstance(feature, str) or not feature.strip()
                        for feature in required_features
                    ):
                        diagnostics.append(
                            _diag(
                                "required_features_invalid",
                                "run.json",
                                "required_features must be a list of non-empty strings",
                            )
                        )
                    elif len(set(required_features)) != len(required_features):
                        diagnostics.append(
                            _diag(
                                "required_features_invalid",
                                "run.json",
                                "required features must be unique",
                            )
                        )
                    else:
                        for feature in sorted(
                            set(required_features) - KNOWN_REQUIRED_FEATURES
                        ):
                            diagnostics.append(
                                _diag("required_feature_unknown", "run.json", feature)
                            )
                    run_id_value = manifest.get("run_id")
                    if not isinstance(run_id_value, str) or not run_id_value.strip():
                        diagnostics.append(_diag("run_id_missing", "run.json"))
                    else:
                        run_id = run_id_value
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                diagnostics.append(_diag("manifest_read_failed", "run.json", str(exc)))

        if "cost.json" in info_by_name:
            try:
                cost_value = _parse_json(
                    "cost.json",
                    archive.read(info_by_name["cost.json"]),
                    diagnostics,
                )
                if cost_value is not None:
                    if not isinstance(cost_value, dict):
                        diagnostics.append(
                            _diag(
                                "cost_evidence_invalid",
                                "cost.json",
                                "cost evidence must be a JSON object",
                            )
                        )
                    else:
                        try:
                            CostEvidence.from_dict(cost_value)
                        except CostValidationError as exc:
                            diagnostics.append(
                                _diag(
                                    "cost_evidence_invalid",
                                    "cost.json",
                                    str(exc),
                                )
                            )
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                diagnostics.append(
                    _diag("manifest_read_failed", "cost.json", str(exc))
                )

        identity_documents: dict[str, dict[str, object]] = {}
        for name in (
            "challenge.json",
            "evaluation/assertions.json",
            "evaluation/capacity-curve.json",
            "captures/overview.json",
        ):
            if name not in info_by_name:
                continue
            try:
                value = _parse_json(name, archive.read(info_by_name[name]), diagnostics)
                if isinstance(value, dict):
                    identity_documents[name] = value
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                diagnostics.append(_diag("manifest_read_failed", name, str(exc)))

        capture = identity_documents.get("captures/overview.json")
        if capture is not None:
            capture_issues = capture_metadata_issues(
                capture,
                require_bundle_fields=True,
            )
            if capture_issues:
                diagnostics.append(
                    _diag(
                        "capture_metadata_invalid",
                        "captures/overview.json",
                        "; ".join(capture_issues),
                    )
                )
            if (
                "captures/overview.png" in info_by_name
                and "captures/overview.webm" in info_by_name
            ):
                try:
                    media_diagnostics = media_issues(
                        archive.read(info_by_name["captures/overview.png"]),
                        archive.read(info_by_name["captures/overview.webm"]),
                        viewport=(
                            capture.get("viewport")
                            if isinstance(capture.get("viewport"), dict)
                            else None
                        ),
                    )
                    diagnostics.extend(
                        _diag(code, f"captures/overview.{ 'png' if 'png' in code else 'webm' }")
                        for code in media_diagnostics
                    )
                except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                    diagnostics.append(
                        _diag("capture_media_read_failed", "captures/", str(exc))
                    )

        if run_manifest is not None and capture is not None:
            required_identity = {
                "selected_candidate_hash": str,
                "challenge": str,
                "scenario_pack": str,
                "scenario_id": str,
                "scenario_profile": str,
                "seed": int,
            }
            missing_identity = [
                key
                for key, expected_type in required_identity.items()
                if isinstance(run_manifest.get(key), bool)
                or not isinstance(run_manifest.get(key), expected_type)
                or (
                    expected_type is str
                    and not str(run_manifest.get(key, "")).strip()
                )
            ]
            if missing_identity:
                diagnostics.append(
                    _diag(
                        "run_capture_identity_missing",
                        "run.json",
                        ", ".join(missing_identity),
                    )
                )
            if capture.get("artifact_hash") != run_manifest.get("selected_candidate_hash"):
                diagnostics.append(
                    _diag("capture_artifact_mismatch", "captures/overview.json")
                )
            artifact_entries = sorted(
                name
                for name in info_by_name
                if name.startswith("artifact/submission/")
            )
            if artifact_entries:
                artifact_digest = hashlib.sha256()
                try:
                    for name in artifact_entries:
                        relative = name.removeprefix("artifact/submission/").encode(
                            "utf-8"
                        )
                        data = archive.read(info_by_name[name])
                        artifact_digest.update(len(relative).to_bytes(8, "big"))
                        artifact_digest.update(relative)
                        artifact_digest.update(len(data).to_bytes(8, "big"))
                        artifact_digest.update(data)
                    if artifact_digest.hexdigest() != run_manifest.get(
                        "selected_candidate_hash"
                    ):
                        diagnostics.append(
                            _diag("artifact_hash_mismatch", "artifact/submission/")
                        )
                except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                    diagnostics.append(
                        _diag("artifact_hash_failed", "artifact/submission/", str(exc))
                    )
            challenge = identity_documents.get("challenge.json", {})
            scenario = challenge.get("scenario", {})
            scenario = scenario if isinstance(scenario, dict) else {}
            assertions = identity_documents.get("evaluation/assertions.json", {})
            capacity = identity_documents.get("evaluation/capacity-curve.json", {})
            comparisons = {
                "challenge": (
                    run_manifest.get("challenge"),
                    capture.get("challenge"),
                    challenge.get("challenge_id"),
                ),
                "scenario_pack": (
                    run_manifest.get("scenario_pack"),
                    challenge.get("scenario_pack"),
                ),
                "scenario_id": (
                    run_manifest.get("scenario_id"),
                    capture.get("scenario_id"),
                    scenario.get("scenario_id"),
                    assertions.get("scenario_id"),
                    capacity.get("scenario_id"),
                ),
                "scenario_profile": (
                    run_manifest.get("scenario_profile"),
                    capture.get("scenario_profile"),
                    scenario.get("profile"),
                    assertions.get("scenario_profile"),
                    capacity.get("scenario_profile"),
                ),
                "seed": (
                    run_manifest.get("seed"),
                    capture.get("seed"),
                    scenario.get("seed"),
                    assertions.get("seed"),
                    capacity.get("seed"),
                ),
            }
            for field, values in comparisons.items():
                if any(value is None for value in values) or not all(
                    value == values[0] for value in values[1:]
                ):
                    diagnostics.append(
                        _diag(
                            "capture_identity_mismatch",
                            "captures/overview.json",
                            field,
                        )
                    )

        refs: list[tuple[str, str]] = []
        for name, info in info_by_name.items():
            if not name.endswith(".json") or not (
                name in P0_REQUIRED_FILES or name.startswith("attempts/") or name.startswith("provenance/")
            ):
                continue
            try:
                value = _parse_json(name, archive.read(info), diagnostics)
                if value is not None:
                    _walk_references(value, name, refs)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                diagnostics.append(_diag("manifest_read_failed", name, str(exc)))
        for source, reference in refs:
            line_match = re.match(r"^(.*):(\d+)$", reference)
            looks_like_line_reference = bool(line_match and "/" in line_match.group(1))
            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", reference) and not looks_like_line_reference:
                diagnostics.append(_diag("external_evidence_reference", source, reference))
                continue
            if "#" in reference:
                base = reference.split("#", 1)[0]
            else:
                base = line_match.group(1) if line_match else reference
            if not base or _safe_member_name(base) is not None or base not in names:
                diagnostics.append(_diag("missing_evidence_reference", source, reference))
        diagnostics.extend(_profile_diagnostics(names))
        return BundleValidationResult(not diagnostics, tuple(diagnostics), tuple(sorted(names)), total_size, run_id)


def _scan_staging(staging: Path, limits: BundleLimits) -> tuple[dict[str, Path], tuple[BundleDiagnostic, ...]]:
    diagnostics: list[BundleDiagnostic] = []
    try:
        staging_mode = staging.lstat().st_mode
    except OSError:
        staging_mode = 0
    if not stat.S_ISDIR(staging_mode):
        return {}, (_diag("staging_not_found", str(staging)),)
    payload: dict[str, Path] = {}
    folded: dict[str, str] = {}
    file_count = 0
    for root, dirs, files in os.walk(staging, topdown=True, followlinks=False):
        root_path = Path(root)
        for directory in list(dirs):
            candidate = root_path / directory
            try:
                mode = candidate.lstat().st_mode
            except OSError as exc:
                diagnostics.append(_diag("staging_stat_failed", str(candidate), str(exc)))
                continue
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                diagnostics.append(_diag("staging_special_file", str(candidate)))
                dirs.remove(directory)
        for filename in files:
            candidate = root_path / filename
            try:
                mode = candidate.lstat().st_mode
            except OSError as exc:
                diagnostics.append(_diag("staging_stat_failed", str(candidate), str(exc)))
                continue
            relative = candidate.relative_to(staging).as_posix()
            if stat.S_ISLNK(mode):
                diagnostics.append(_diag("staging_symlink", relative))
                continue
            if not stat.S_ISREG(mode):
                diagnostics.append(_diag("staging_special_file", relative))
                continue
            path_diag = _safe_member_name(relative)
            if path_diag is not None:
                diagnostics.append(path_diag)
                continue
            if _member_key(relative) == _member_key(CHECKSUMS_NAME):
                diagnostics.append(_diag("reserved_inventory_path", relative))
                continue
            file_count += 1
            if file_count > limits.max_entries - 1:
                diagnostics.append(_diag("entry_limit", str(staging)))
                continue
            if _member_key(relative) in folded:
                diagnostics.append(_diag("case_collision", relative, folded[_member_key(relative)]))
                continue
            folded[_member_key(relative)] = relative
            if candidate.stat().st_size > limits.max_file_size:
                diagnostics.append(_diag("file_size_limit", relative))
            payload[relative] = candidate
    try:
        total_size = sum(path.stat().st_size for path in payload.values())
    except OSError as exc:
        diagnostics.append(_diag("staging_stat_failed", str(staging), str(exc)))
        total_size = limits.max_total_size + 1
    if total_size > limits.max_total_size:
        diagnostics.append(_diag("total_size_limit", str(staging)))
    diagnostics.extend(_profile_diagnostics(set(payload)))
    return payload, tuple(diagnostics)


def _read_staging_file(name: str, path: Path, limits: BundleLimits) -> bytes:
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise BundleValidationError(_diag("staging_special_file", name))
        if before.st_size > limits.max_file_size:
            raise BundleValidationError(_diag("file_size_limit", name))
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            data = stream.read(limits.max_file_size + 1)
            after = os.fstat(stream.fileno())
    except BundleValidationError:
        raise
    except OSError as exc:
        raise BundleValidationError(_diag("staging_read_failed", name, str(exc))) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(data) > limits.max_file_size or after.st_size > limits.max_file_size:
        raise BundleValidationError(_diag("file_size_limit", name))
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or after.st_size != len(data):
        raise BundleValidationError(_diag("staging_changed", name))
    return data


def _write_deterministic_zip(payload: Mapping[str, Path], destination: Path,
                             limits: BundleLimits) -> None:
    inventory: list[str] = []
    contents: dict[str, bytes] = {}
    total_size = 0
    for name in sorted(payload):
        data = _read_staging_file(name, payload[name], limits)
        contents[name] = data
        total_size += len(data)
    if total_size > limits.max_total_size:
        raise BundleValidationError(_diag("total_size_limit", str(destination)))
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, allowZip64=False) as archive:
        for name in sorted(contents):
            data = contents[name]
            inventory.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.create_version = info.extract_version = 20
            info.flag_bits = 0x800
            # Highly repetitive model-generated HTML/JSON can compress beyond
            # the validator's zip-bomb ratio limit. Store such legitimate
            # entries instead of weakening that safety limit.
            compressed_size = len(zlib.compress(data, level=9)) if data else 0
            compression = (
                zipfile.ZIP_STORED
                if data and compressed_size and len(data) / compressed_size > limits.max_compression_ratio
                else zipfile.ZIP_DEFLATED
            )
            info.compress_type = compression
            info.external_attr = 0o100644 << 16
            info.extra = info.comment = b""
            archive.writestr(
                info,
                data,
                compress_type=compression,
                compresslevel=9 if compression == zipfile.ZIP_DEFLATED else None,
            )
        info = zipfile.ZipInfo(CHECKSUMS_NAME, (1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.create_version = info.extract_version = 20
        info.flag_bits = 0x800
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        info.extra = info.comment = b""
        archive.writestr(info, "".join(inventory).encode(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def finalize_bundle(staging_dir: os.PathLike[str] | str, output_path: os.PathLike[str] | str,
                    limits: BundleLimits | None = None) -> FinalizedBundle:
    """Finalize a prepared tree, independently validate it, then install once."""
    limits = limits or BundleLimits()
    staging, output = Path(staging_dir), Path(output_path)
    if output.suffixes[-2:] != [".ralph", ".zip"]:
        raise BundleError(_diag("invalid_output_suffix", str(output)))
    if output.exists():
        raise BundleError(_diag("output_exists", str(output)))
    output.parent.mkdir(parents=True, exist_ok=True)
    payload, diagnostics = _scan_staging(staging, limits)
    if diagnostics:
        raise BundleValidationError(diagnostics)
    fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    os.close(fd)
    temporary = Path(temp_name)
    try:
        _write_deterministic_zip(payload, temporary, limits)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        result = validate_bundle(temporary, limits)
        result.require_valid()
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        try:
            os.link(temporary, output)  # atomic, non-overwriting install
        except FileExistsError:
            raise BundleError(_diag("output_exists", str(output))) from None
        temporary.unlink()
        return FinalizedBundle(output, digest, result.entries)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def safe_extract_bundle(bundle_path: os.PathLike[str] | str, destination: os.PathLike[str] | str,
                        limits: BundleLimits | None = None) -> ExtractedBundle:
    """Validate fully, then extract payload bytes into a new directory."""
    limits = limits or BundleLimits()
    bundle = Path(bundle_path)
    try:
        validated_stat = bundle.lstat()
    except OSError as exc:
        raise BundleValidationError(_diag("bundle_not_found", str(bundle), str(exc))) from exc
    validation = validate_bundle(bundle, limits)
    validation.require_valid()
    target = Path(destination)
    if target.exists():
        raise BundleError(_diag("extraction_exists", str(target)))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(bundle, flags)
        opened_stat = os.fstat(descriptor)
        validated_identity = (
            validated_stat.st_dev,
            validated_stat.st_ino,
            validated_stat.st_size,
            validated_stat.st_mtime_ns,
        )
        opened_identity = (
            opened_stat.st_dev,
            opened_stat.st_ino,
            opened_stat.st_size,
            opened_stat.st_mtime_ns,
        )
        if validated_identity != opened_identity:
            raise BundleValidationError(_diag("bundle_changed", str(bundle)))
        with os.fdopen(descriptor, "rb", closefd=True) as bundle_stream:
            descriptor = -1
            with zipfile.ZipFile(bundle_stream, "r") as archive:
                for name in validation.entries:
                    output = temporary.joinpath(*PurePosixPath(name).parts)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(archive.getinfo(name), "r") as source, output.open("xb") as dest:
                        shutil.copyfileobj(source, dest, length=1024 * 1024)
        os.rename(temporary, target)
        return ExtractedBundle(target, validation.entries)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
__all__ = [
    "BundleDiagnostic", "BundleError", "BundleLimits", "BundleValidationError",
    "BundleValidationResult", "ExtractedBundle", "FinalizedBundle", "P0_REQUIRED_FILES",
    "finalize_bundle", "safe_extract_bundle", "validate_bundle",
]
