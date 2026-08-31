"""Killable Playwright worker for ``gates/v1`` monitoring and capture."""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
import json
import mimetypes
from pathlib import Path, PurePosixPath
import shutil
import time
from typing import Any
from urllib.parse import unquote, urlsplit

from playwright.sync_api import Page, Route, sync_playwright

from .gate_bridge import GATES_INIT_SCRIPT
from .conformance import evaluate_public_conformance
from .gate_evaluator import evaluate_gate_monitor
from .gates import GateScenario, build_balanced_gate_scenario, gate_scenario_from_dict


_ORIGIN = "http://candidate.invalid"
_VIEWPORT = {"width": 1440, "height": 900}
_MONITOR_INTERVAL_MS = 250
_READY_TIMEOUT_MS = 5_000
_VIDEO_FRAME_RATE_FPS = 25
_CAPTURE_WORKER_PROTOCOL = "browser-worker/v2"


def _worker_version() -> str:
    """Return package evidence without requiring an installed distribution."""

    try:
        return package_version("ralph-bench")
    except PackageNotFoundError:
        # The CLI is intentionally usable from a source checkout during local
        # development and fixture tests.  Do not turn that valid mode into a
        # browser infrastructure failure merely because wheel metadata is absent.
        return "source-checkout"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class WorkerError(RuntimeError):
    pass


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )


class CandidateRouter:
    """Fulfil one synthetic origin solely from regular candidate files."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.blocked: list[str] = []

    def __call__(self, route: Route) -> None:
        request = route.request
        parsed = urlsplit(request.url)
        if parsed.scheme != "http" or parsed.netloc != "candidate.invalid":
            self.blocked.append(f"{parsed.scheme}://{parsed.netloc}{parsed.path}"[:500])
            route.abort("blockedbyclient")
            return
        decoded = unquote(parsed.path).lstrip("/") or "index.html"
        logical = PurePosixPath(decoded)
        if logical.is_absolute() or any(part in {"", ".", ".."} for part in logical.parts):
            route.fulfill(status=404, body=b"not found", content_type="text/plain")
            return
        candidate = self.root.joinpath(*logical.parts)
        try:
            resolved = candidate.resolve(strict=True)
            valid = resolved.is_file() and not candidate.is_symlink() and resolved.is_relative_to(self.root)
        except OSError:
            valid = False
        if not valid:
            route.fulfill(status=404, body=b"not found", content_type="text/plain")
            return
        mime = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        route.fulfill(status=200, body=resolved.read_bytes(), content_type=mime)


def _prepare_page(
    context: Any,
    candidate: Path,
) -> tuple[Page, CandidateRouter, list[str], list[dict[str, str]]]:
    context.add_init_script(script=GATES_INIT_SCRIPT)
    page = context.new_page()
    router = CandidateRouter(candidate)
    runtime_errors: list[str] = []
    console: list[dict[str, str]] = []
    page.route("**/*", router)
    if hasattr(page, "route_web_socket"):
        page.route_web_socket("**/*", lambda socket: socket.close())
    page.on("pageerror", lambda error: runtime_errors.append(f"pageerror:{str(error)[:1000]}"))
    page.on(
        "console",
        lambda message: console.append({"type": message.type, "text": message.text[:2000]}),
    )
    page.goto(f"{_ORIGIN}/index.html", wait_until="domcontentloaded", timeout=10_000)
    return page, router, runtime_errors, console


def _driver_call(page: Page, method: str, *args: Any) -> Any:
    return page.evaluate(
        """async ({method, args}) => {
          const driver = globalThis.__RALPH_GATES_DRIVER__;
          if (!driver || driver.apiVersion !== "gates/v1") {
            throw new Error("evaluator gates/v1 driver is unavailable");
          }
          const fn = driver[method];
          if (typeof fn !== "function") throw new Error(`unknown gates driver method: ${method}`);
          return await fn.apply(driver, args);
        }""",
        {"method": method, "args": list(args)},
    )


def _arrival_schedule(scenario: GateScenario) -> list[tuple[int, str, dict[str, str]]]:
    values = [
        (item.arrival_ms, "car", item.to_public_dict()) for item in scenario.cars
    ] + [
        (item.arrival_ms, "pedestrian", item.to_public_dict())
        for item in scenario.pedestrians
    ]
    return sorted(values, key=lambda item: (item[0], item[1], item[2]["id"]))


def _monitor_and_capture(
    browser: Any,
    candidate: Path,
    output: Path,
    scenario: GateScenario,
    evaluation_mode: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str], list[dict[str, str]], list[str]]:
    started = time.monotonic()
    video_root = output / ".video"
    video_root.mkdir()
    context = browser.new_context(
        viewport=_VIEWPORT,
        record_video_dir=str(video_root),
        record_video_size=_VIEWPORT,
        service_workers="block",
        offline=True,
    )
    page, router, runtime_errors, console = _prepare_page(context, candidate)
    video = page.video
    observations: list[dict[str, Any]] = []
    monitor: dict[str, Any] = {
        "api_version": "gates/v1",
        "ready": False,
        "issued": [],
        "completions": [],
        "invalid": [],
    }
    readiness_error: str | None = None
    poster_at_ms = 0
    try:
        try:
            page.wait_for_function(
                "() => globalThis.__RALPH_GATES_DRIVER__?.ready() === true",
                timeout=_READY_TIMEOUT_MS,
            )
        except Exception as exc:
            readiness_error = f"{type(exc).__name__}: gates/v1 callbacks were not registered"[:1000]
        if readiness_error is None:
            _driver_call(page, "start")
            arrivals = _arrival_schedule(scenario)
            next_arrival = 0
            run_started = time.monotonic()
            poster_target = 34_000
            while True:
                elapsed_ms = min(
                    scenario.horizon_ms,
                    max(0, round((time.monotonic() - run_started) * 1_000)),
                )
                while next_arrival < len(arrivals) and arrivals[next_arrival][0] <= elapsed_ms:
                    _, kind, request = arrivals[next_arrival]
                    _driver_call(page, "addCar" if kind == "car" else "addPedestrian", request)
                    next_arrival += 1
                snapshot = _driver_call(page, "snapshot")
                snapshot["time_ms"] = elapsed_ms
                snapshot["runtime_error_count"] = len(runtime_errors)
                snapshot["network_violation_count"] = len(router.blocked)
                observations.append(snapshot)
                if poster_at_ms == 0 and elapsed_ms >= poster_target:
                    page.screenshot(path=str(output / "overview.png"), full_page=False)
                    poster_at_ms = elapsed_ms
                if elapsed_ms >= scenario.horizon_ms:
                    break
                page.wait_for_timeout(min(_MONITOR_INTERVAL_MS, scenario.horizon_ms - elapsed_ms))
            monitor = _driver_call(page, "final")
        else:
            runtime_errors.append(readiness_error)
            page.wait_for_timeout(1_000)
            monitor = _driver_call(page, "final")
    finally:
        if not (output / "overview.png").exists():
            page.screenshot(path=str(output / "overview.png"), full_page=False)
        context.close()
    if video is None:
        raise WorkerError("Playwright did not create a video artifact")
    video.save_as(str(output / "overview.webm"))
    shutil.rmtree(video_root, ignore_errors=True)
    if evaluation_mode == "gates":
        evaluation = evaluate_gate_monitor(
            scenario,
            monitor,
            observations,
            runtime_errors=runtime_errors,
            network_violations=router.blocked,
        ).to_dict()
    elif evaluation_mode == "conformance":
        evaluation = evaluate_public_conformance(
            scenario,
            monitor,
            observations,
            runtime_errors=runtime_errors,
            network_violations=router.blocked,
        )
    else:
        raise WorkerError(f"unsupported evaluation mode: {evaluation_mode!r}")
    duration_ms = max(1, round((time.monotonic() - started) * 1_000))
    capture = {
        "schema_version": "capture/v1",
        "viewport": _VIEWPORT,
        "scenario_id": scenario.scenario_id,
        "scenario_profile": scenario.profile,
        "seed": scenario.seed,
        "simulated_horizon_ms": scenario.horizon_ms,
        "poster_simulation_ms": poster_at_ms,
        "simulation_interval_ms": {
            "start": 0,
            "end": scenario.horizon_ms,
            "step": _MONITOR_INTERVAL_MS,
        },
        "simulation_phase": (
            "public-conformance"
            if evaluation_mode == "conformance"
            else "gates-load-and-capture"
        ),
        "evaluation_mode": evaluation_mode,
        "playback_step_ms": _MONITOR_INTERVAL_MS,
        "playback_delay_ms": _MONITOR_INTERVAL_MS,
        "playback_rate": 1,
        "duration_ms": duration_ms,
        "frame_rate_fps": _VIDEO_FRAME_RATE_FPS,
        "capture_worker": {
            "id": "ralph-bench.browser-worker",
            "protocol": _CAPTURE_WORKER_PROTOCOL,
            "version": _worker_version(),
        },
        "network_violations": list(router.blocked),
        "runtime_errors": list(runtime_errors),
        "console": console,
        "interface": "gates/v1",
        "monitor_observation_count": len(observations),
    }
    return evaluation, monitor, capture, runtime_errors, console, list(router.blocked)


def run_worker(
    candidate: Path,
    output: Path,
    chromium: Path,
    seed: int,
    *,
    scenario: GateScenario | None = None,
    evaluation_mode: str = "gates",
) -> dict[str, Any]:
    if not candidate.is_dir() or candidate.is_symlink():
        raise WorkerError("candidate must be a real directory")
    if output.exists():
        raise WorkerError("browser output directory already exists")
    output.mkdir(parents=True)
    scenario = scenario or build_balanced_gate_scenario(seed)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=(
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-default-apps",
                "--disable-features=Translate,MediaRouter,OptimizationHints",
                "--disable-sync",
                "--host-resolver-rules=MAP * ~NOTFOUND",
                "--no-first-run",
            ),
        )
        browser_version = browser.version
        evaluation, monitor, capture, errors, console, blocked = _monitor_and_capture(
            browser, candidate, output, scenario, evaluation_mode
        )
        browser.close()
    capture.update(
        {
            "browser": "chromium",
            "browser_version": browser_version,
            "executable_sha256": _file_sha256(chromium),
            "playwright_version": package_version("playwright"),
        }
    )
    result = {
        "schema_version": "browser-evaluation/v2",
        "protocol": "gates/v1",
        "evaluation": evaluation,
        "scenario": scenario.to_dict(),
        "monitor": monitor,
        "browser": {
            "name": "chromium",
            "version": browser_version,
            "playwright_version": package_version("playwright"),
            "executable": chromium.name,
            "console": console,
            "page_errors": errors,
            "network_violations": blocked,
        },
        "capture": capture,
    }
    _write_json(output / "result.json", result)
    _write_json(output / "overview.json", capture)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ralph-bench-browser-worker")
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--chromium", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--scenario", type=Path)
    parser.add_argument(
        "--evaluation-mode",
        choices=("gates", "conformance"),
        default="gates",
    )
    args = parser.parse_args(argv)
    try:
        scenario = None
        if args.scenario is not None:
            scenario = gate_scenario_from_dict(
                json.loads(args.scenario.read_text(encoding="utf-8"))
            )
        run_worker(
            args.candidate,
            args.output,
            args.chromium,
            args.seed,
            scenario=scenario,
            evaluation_mode=args.evaluation_mode,
        )
    except Exception as exc:
        print(f"browser worker failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
