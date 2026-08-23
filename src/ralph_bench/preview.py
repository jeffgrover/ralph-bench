"""Safe local viewing of evaluator-recorded bundle media."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import tempfile
import webbrowser

from .bundles import BundleError, BundleValidationError, safe_extract_bundle


class PreviewError(RuntimeError):
    """A validated result could not be prepared or opened for viewing."""


@dataclass(frozen=True, slots=True)
class PreparedPreview:
    media_path: Path
    extraction_root: Path


def prepare_bundle_preview(bundle: Path) -> PreparedPreview:
    """Validate a bundle and extract its recorded overview into temporary storage."""

    parent = Path(tempfile.mkdtemp(prefix="ralph-bench-preview-"))
    target = parent / "bundle"
    try:
        extracted = safe_extract_bundle(bundle, target)
    except (BundleError, BundleValidationError, OSError) as exc:
        raise PreviewError(f"could not prepare bundle preview: {exc}") from exc
    media = extracted.path / "captures" / "overview.webm"
    if not media.is_file() or media.is_symlink():
        raise PreviewError("validated bundle has no regular recorded overview")
    return PreparedPreview(media.resolve(), parent)


def open_bundle_preview(
    bundle: Path,
    *,
    opener: Callable[[str], bool] = webbrowser.open_new_tab,
) -> PreparedPreview:
    """Open the evaluator-recorded overview without executing candidate HTML."""

    preview = prepare_bundle_preview(bundle)
    try:
        opened = opener(preview.media_path.as_uri())
    except Exception as exc:
        raise PreviewError(
            f"browser launch failed; recorded overview remains at {preview.media_path}"
        ) from exc
    if not opened:
        raise PreviewError(
            f"no default browser accepted the preview; recorded overview remains at {preview.media_path}"
        )
    return preview


__all__ = [
    "PreparedPreview",
    "PreviewError",
    "open_bundle_preview",
    "prepare_bundle_preview",
]
