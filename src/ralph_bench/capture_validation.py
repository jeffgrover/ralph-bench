"""Shared semantic checks for human-review capture evidence."""

from __future__ import annotations

import math
import re
from typing import Any, Mapping


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
WEBM_EBML_SIGNATURE = b"\x1a\x45\xdf\xa3"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    if (
        len(data) < 24
        or not data.startswith(PNG_SIGNATURE)
        or data[12:16] != b"IHDR"
    ):
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return (width, height) if width > 0 and height > 0 else None


def is_webm(data: bytes) -> bool:
    return data.startswith(WEBM_EBML_SIGNATURE) and b"webm" in data[:4096].lower()


def capture_metadata_issues(
    value: object,
    *,
    require_bundle_fields: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ("capture metadata must be an object",)
    issues: list[str] = []

    def text_field(name: str) -> str | None:
        item = value.get(name)
        if not isinstance(item, str) or not item.strip():
            issues.append(f"{name} must be a non-empty string")
            return None
        return item

    def positive_number(name: str) -> float | None:
        item = value.get(name)
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            or item <= 0
        ):
            issues.append(f"{name} must be a positive finite number")
            return None
        return float(item)

    if value.get("schema_version") != "capture/v1":
        issues.append("schema_version must be capture/v1")
    text_field("scenario_id")
    text_field("scenario_profile")
    text_field("simulation_phase")
    text_field("browser")
    text_field("browser_version")
    text_field("playwright_version")
    seed = value.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        issues.append("seed must be an integer")
    horizon = positive_number("simulated_horizon_ms")
    positive_number("playback_step_ms")
    positive_number("playback_delay_ms")
    positive_number("playback_rate")
    positive_number("duration_ms")
    positive_number("frame_rate_fps")

    viewport = value.get("viewport")
    if not isinstance(viewport, Mapping) or any(
        isinstance(viewport.get(key), bool)
        or not isinstance(viewport.get(key), int)
        or viewport.get(key, 0) <= 0
        for key in ("width", "height")
    ):
        issues.append("viewport must contain positive integer width and height")

    interval = value.get("simulation_interval_ms")
    if not isinstance(interval, Mapping):
        issues.append("simulation_interval_ms must be an object")
    else:
        start, end, step = (
            interval.get("start"),
            interval.get("end"),
            interval.get("step"),
        )
        if start != 0 or isinstance(end, bool) or not isinstance(end, int) or end <= 0:
            issues.append("simulation interval must start at zero and have a positive integer end")
        if isinstance(step, bool) or not isinstance(step, int) or step <= 0:
            issues.append("simulation interval step must be a positive integer")
        if horizon is not None and end != int(horizon):
            issues.append("simulation interval end must match simulated_horizon_ms")

    worker = value.get("capture_worker")
    if not isinstance(worker, Mapping) or any(
        not isinstance(worker.get(key), str) or not worker.get(key, "").strip()
        for key in ("id", "protocol", "version")
    ):
        issues.append("capture_worker must identify id, protocol, and version")

    if require_bundle_fields:
        text_field("challenge")
        artifact_hash = value.get("artifact_hash")
        if not isinstance(artifact_hash, str) or _SHA256.fullmatch(artifact_hash) is None:
            issues.append("artifact_hash must be a lowercase SHA-256 digest")
        refs = value.get("evidence_refs")
        if not isinstance(refs, list) or not refs or any(
            not isinstance(item, str) or not item.strip() for item in refs
        ):
            issues.append("evidence_refs must be a non-empty string list")
    return tuple(issues)


def media_issues(
    png: bytes,
    webm: bytes,
    *,
    viewport: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    dimensions = png_dimensions(png)
    if dimensions is None:
        issues.append("invalid_png")
    elif viewport is not None and dimensions != (
        viewport.get("width"),
        viewport.get("height"),
    ):
        issues.append("png_viewport_mismatch")
    if not is_webm(webm):
        issues.append("invalid_webm")
    return tuple(issues)


__all__ = [
    "PNG_SIGNATURE",
    "WEBM_EBML_SIGNATURE",
    "capture_metadata_issues",
    "is_webm",
    "media_issues",
    "png_dimensions",
]
