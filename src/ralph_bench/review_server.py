"""Local, read-only serving of one bundle to the human review page."""

from __future__ import annotations

from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import tempfile
from typing import Callable
import webbrowser

from .bundles import BundleError, BundleValidationError, safe_extract_bundle


class ReviewServerError(RuntimeError):
    """A review source could not be prepared safely."""


@dataclass(frozen=True, slots=True)
class PreparedReview:
    root: Path
    url: str


def _copy_inputs(source: Path, destination: Path) -> None:
    required = (
        source / "run.json",
        source / "captures" / "overview.json",
        source / "captures" / "overview.webm",
    )
    if any(not path.is_file() or path.is_symlink() for path in required):
        raise ReviewServerError(
            "review source must contain run.json, captures/overview.json, "
            "and captures/overview.webm"
        )
    (destination / "captures").mkdir(parents=True)
    shutil.copy2(required[0], destination / "run.json")
    shutil.copy2(required[1], destination / "captures" / "overview.json")
    shutil.copy2(required[2], destination / "captures" / "overview.webm")


def prepare_review(source: Path, project_root: Path) -> PreparedReview:
    """Prepare only review metadata/media in a temporary local web root."""

    source = Path(source).resolve()
    project_root = Path(project_root).resolve()
    page = project_root / "review" / "index.html"
    if not page.is_file():
        raise ReviewServerError(f"review page is missing: {page}")
    temporary = Path(tempfile.mkdtemp(prefix="ralph-bench-review-"))
    try:
        shutil.copy2(page, temporary / "index.html")
        run_root = temporary / "run"
        if source.is_file() and source.suffix.lower() == ".zip":
            extracted = temporary / "extracted"
            safe_extract_bundle(source, extracted)
            _copy_inputs(extracted, run_root)
            shutil.rmtree(extracted)
        elif source.is_dir():
            bundles = sorted(source.glob("*.ralph.zip"))
            if bundles:
                if len(bundles) != 1:
                    raise ReviewServerError(
                        "review directory contains multiple bundles; pass one .ralph.zip"
                    )
                extracted = temporary / "extracted"
                safe_extract_bundle(bundles[0], extracted)
                _copy_inputs(extracted, run_root)
                shutil.rmtree(extracted)
            else:
                _copy_inputs(source, run_root)
        else:
            raise ReviewServerError(f"review source does not exist: {source}")
    except ReviewServerError:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    except (BundleError, BundleValidationError, OSError) as exc:
        shutil.rmtree(temporary, ignore_errors=True)
        raise ReviewServerError(f"could not prepare review source: {exc}") from exc
    url = (
        "http://127.0.0.1:0/?video=/run/captures/overview.webm"
        "&run=/run/run.json&capture=/run/captures/overview.json"
    )
    return PreparedReview(temporary, url)


def serve_review(
    source: Path,
    *,
    project_root: Path,
    opener: Callable[[str], bool] = webbrowser.open_new_tab,
    output: Callable[[str], None] = print,
    open_browser: bool = True,
) -> None:
    """Serve one prepared review until the operator presses Ctrl-C."""

    prepared = prepare_review(source, project_root)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(prepared.root), **kwargs)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = prepared.url.replace(":0/", f":{server.server_port}/")
    try:
        if open_browser:
            opener(url)
        output(f"Human review: {url}")
        output("Press Ctrl-C when the review is complete.")
        server.serve_forever()
    except KeyboardInterrupt:
        output("Human review server stopped.")
    finally:
        server.server_close()
        shutil.rmtree(prepared.root, ignore_errors=True)


__all__ = ["PreparedReview", "ReviewServerError", "prepare_review", "serve_review"]
