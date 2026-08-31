"""Parent-side lifecycle for the killable Playwright evaluation worker."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

from .capture_validation import capture_metadata_issues, media_issues
from .gates import GateScenario


class BrowserRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BrowserEvaluationArtifacts:
    result: dict[str, Any]
    result_path: Path
    overview_video: Path
    overview_poster: Path
    overview_metadata: Path
    stdout_path: Path
    stderr_path: Path
    wall_seconds: float


def find_chromium() -> Path:
    # Prefer Playwright's own browser build for evaluator work. On macOS the
    # user's Google Chrome app can abort while being launched headlessly by a
    # non-UI parent; the managed Chromium binary is isolated from that app
    # lifecycle and is the reproducible choice for Ralph.
    headless_patterns = (
        "chromium_headless_shell-*/**/chrome-headless-shell",
        "chromium_headless_shell-*/**/headless_shell",
    )
    managed_patterns = (
        "chromium-*/chrome-linux*/chrome",
        "chromium-*/chrome-mac*/chrome",
        "chromium-*/**/Contents/MacOS/Chromium",
        "chromium-*/**/Contents/MacOS/Google Chrome for Testing",
    )
    managed_headless = sorted(
        {
            path
            for root in _playwright_cache_roots()
            for pattern in headless_patterns
            for path in root.glob(pattern)
            if path.is_file() and os.access(path, os.X_OK)
        },
        key=lambda path: path.as_posix(),
        reverse=True,
    )
    managed = managed_headless + sorted(
        {
            path
            for root in _playwright_cache_roots()
            for pattern in managed_patterns
            for path in root.glob(pattern)
            if path.is_file() and os.access(path, os.X_OK)
        },
        key=lambda path: path.as_posix(),
        reverse=True,
    )
    candidates = (
        os.environ.get("RALPH_BENCH_CHROMIUM"),
        *(str(path) for path in managed),
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/opt/google/chrome/chrome",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        str(Path.home() / "Applications/Chromium.app/Contents/MacOS/Chromium"),
    )
    for value in candidates:
        if not value:
            continue
        path = Path(value)
        if path.is_file() and os.access(path, os.X_OK):
            return path.resolve()
    raise BrowserRuntimeError(
        "no supported Chromium executable was found; install Playwright Chromium "
        "or set RALPH_BENCH_CHROMIUM"
    )


def _playwright_cache_roots() -> tuple[Path, ...]:
    candidates = (
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH"),
        str(Path(os.environ["XDG_CACHE_HOME"]) / "ms-playwright")
        if os.environ.get("XDG_CACHE_HOME")
        else None,
        str(Path.home() / ".cache" / "ms-playwright"),
        str(Path.home() / "Library" / "Caches" / "ms-playwright"),
    )
    roots: list[Path] = []
    for value in candidates:
        if not value or value == "0":
            continue
        root = Path(value)
        try:
            resolved = root.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def find_playwright_browsers_path() -> Path:
    for root in _playwright_cache_roots():
        if any(
            path.is_file() and os.access(path, os.X_OK)
            for path in root.glob("ffmpeg-*/ffmpeg-*")
        ):
            return root
    raise BrowserRuntimeError(
        "Playwright's FFmpeg runtime was not found; run `playwright install ffmpeg`"
    )


def _terminate_group(process: subprocess.Popen[Any]) -> None:
    try:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _worker_failure_detail(*paths: Path) -> str:
    """Return bounded operator-facing worker output before temp cleanup."""

    chunks: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if text:
            chunks.append(text)
    return " ".join(" ".join(chunks).split())[-2_000:]


def run_browser_evaluation(
    candidate: Path,
    output: Path,
    *,
    raw_evidence: Path,
    timeout_seconds: float = 90.0,
    seed: int = 17,
    chromium: Path | None = None,
    playwright_browsers_path: Path | None = None,
    scenario: GateScenario | None = None,
    evaluation_mode: str = "gates",
) -> BrowserEvaluationArtifacts:
    """Evaluate/capture one candidate in a separately killable process tree."""

    if timeout_seconds <= 0:
        raise BrowserRuntimeError("browser timeout must be positive")
    if evaluation_mode not in {"gates", "conformance"}:
        raise BrowserRuntimeError(f"unsupported browser evaluation mode: {evaluation_mode!r}")
    candidate = candidate.resolve()
    output = output.resolve()
    raw_evidence = raw_evidence.resolve()
    chromium = chromium or find_chromium()
    playwright_browsers_path = (
        playwright_browsers_path or find_playwright_browsers_path()
    )
    raw_evidence.mkdir(parents=True, exist_ok=True)
    scenario_path: Path | None = None
    if scenario is not None:
        scenario_path = raw_evidence / "scenario-input.json"
        scenario_path.write_text(
            json.dumps(scenario.to_dict(), ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    # Keep each browser attempt's HOME separate. A single run can evaluate an
    # initial candidate and a repair candidate in succession; sharing this
    # directory makes the second evaluation fail while creating HOME.
    worker_home = raw_evidence / "browser-home"
    worker_home.mkdir(mode=0o700)
    # Chrome creates Unix-domain singleton sockets beneath TMPDIR.  Keep this
    # evaluator-owned path short: staged run UUID paths can exceed Linux's
    # socket path limit before Chrome even starts.
    worker_tmp = Path(tempfile.mkdtemp(prefix="rb-browser-", dir="/tmp"))
    stdout_path = raw_evidence / "browser-worker.stdout.txt"
    stderr_path = raw_evidence / "browser-worker.stderr.txt"
    argv = (
        sys.executable,
        "-m",
        "ralph_bench.browser_worker",
        "--candidate",
        str(candidate),
        "--output",
        str(output),
        "--chromium",
        str(chromium),
        "--seed",
        str(seed),
        "--evaluation-mode",
        evaluation_mode,
    )
    if scenario_path is not None:
        argv += ("--scenario", str(scenario_path))
    start = time.monotonic()
    worker_environment = {
        "PATH": os.defpath,
        "HOME": str(worker_home),
        "XDG_CACHE_HOME": str(worker_home / ".cache"),
        "XDG_CONFIG_HOME": str(worker_home / ".config"),
        "XDG_DATA_HOME": str(worker_home / ".local/share"),
        "TMPDIR": str(worker_tmp),
        "PLAYWRIGHT_BROWSERS_PATH": str(playwright_browsers_path),
    }
    # The parent CLI is supported from both an installed distribution and a
    # source checkout.  The worker has a deliberately minimal environment, so
    # carry only Ralph's import root across rather than inheriting the entire
    # parent PYTHONPATH (which may expose unrelated operator paths).
    worker_environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    for key in ("LANG", "LC_ALL", "LC_CTYPE", "TZ"):
        if key in os.environ:
            worker_environment[key] = os.environ[key]
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                cwd=output.parent,
                env=worker_environment,
                start_new_session=True,
                text=True,
            )
            try:
                returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                _terminate_group(process)
                raise BrowserRuntimeError(
                    f"browser evaluation exceeded {timeout_seconds:g} seconds"
                ) from exc
            except BaseException:
                _terminate_group(process)
                raise
    finally:
        shutil.rmtree(worker_tmp, ignore_errors=True)
    wall = time.monotonic() - start
    if returncode != 0:
        detail = _worker_failure_detail(stdout_path, stderr_path)
        suffix = f": {detail}" if detail else ""
        raise BrowserRuntimeError(
            f"browser worker exited with status {returncode}{suffix}"
        )
    paths = {
        "result": output / "result.json",
        "video": output / "overview.webm",
        "poster": output / "overview.png",
        "metadata": output / "overview.json",
    }
    missing = [name for name, path in paths.items() if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise BrowserRuntimeError(
            "browser worker omitted required artifact(s): " + ", ".join(missing)
        )
    try:
        result = json.loads(paths["result"].read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrowserRuntimeError("browser result is not valid JSON") from exc
    if not isinstance(result, dict) or result.get("schema_version") != "browser-evaluation/v2":
        raise BrowserRuntimeError("browser result has an unsupported schema")
    if result.get("protocol") != "gates/v1":
        raise BrowserRuntimeError("browser result does not use gates/v1")
    try:
        capture = json.loads(paths["metadata"].read_text(encoding="utf-8"))
        png = paths["poster"].read_bytes()
        webm = paths["video"].read_bytes()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrowserRuntimeError("browser capture evidence is unreadable") from exc
    metadata_issues = capture_metadata_issues(capture)
    if metadata_issues:
        raise BrowserRuntimeError(
            "browser capture metadata is invalid: " + "; ".join(metadata_issues)
        )
    if result.get("capture") != capture:
        raise BrowserRuntimeError("browser result and capture metadata disagree")
    scenario = result.get("scenario")
    evaluation = result.get("evaluation")
    if not isinstance(scenario, dict) or not isinstance(evaluation, dict):
        raise BrowserRuntimeError("browser result omitted scenario or evaluation evidence")
    if evaluation.get("outcome") not in {"passed", "failed"}:
        raise BrowserRuntimeError("browser evaluation outcome is invalid")
    if any(
        value != capture.get("seed")
        for value in (scenario.get("seed"), evaluation.get("seed"))
    ) or any(
        value != capture.get("scenario_id")
        for value in (scenario.get("scenario_id"), evaluation.get("scenario_id"))
    ):
        raise BrowserRuntimeError("browser scenario, evaluation, and capture disagree")
    viewport = capture.get("viewport")
    media_diagnostics = media_issues(
        png,
        webm,
        viewport=viewport if isinstance(viewport, dict) else None,
    )
    if media_diagnostics:
        raise BrowserRuntimeError(
            "browser media is invalid: " + ", ".join(media_diagnostics)
        )
    return BrowserEvaluationArtifacts(
        result,
        paths["result"],
        paths["video"],
        paths["poster"],
        paths["metadata"],
        stdout_path,
        stderr_path,
        wall,
    )


__all__ = [
    "BrowserEvaluationArtifacts",
    "BrowserRuntimeError",
    "find_chromium",
    "find_playwright_browsers_path",
    "run_browser_evaluation",
]
