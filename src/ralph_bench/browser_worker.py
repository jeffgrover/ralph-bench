"""Isolated Playwright worker for deterministic traffic observation/capture.

The conductor launches this module in a dedicated process group.  That is a
deliberate reliability boundary: hostile or simply broken candidate
JavaScript can block a renderer indefinitely, so the parent must be able to
terminate the worker and every Chromium child on a hard timeout.
"""

from __future__ import annotations

import argparse
from importlib.metadata import version as package_version
import json
import mimetypes
from pathlib import Path, PurePosixPath
import shutil
import time
from typing import Any
from urllib.parse import unquote, urlsplit

from playwright.sync_api import Page, Route, sync_playwright

from .traffic import (
    NetworkDescription,
    build_balanced_scenario,
    busy_intersection_network,
)
from .traffic_evaluator import evaluate_transport


_ORIGIN = "http://candidate.invalid"
_VIEWPORT = {"width": 1440, "height": 900}
_CAPTURE_STEP_MS = 10_000
_CAPTURE_DELAY_MS = 60
_VIDEO_FRAME_RATE_FPS = 25
_CAPTURE_WORKER_PROTOCOL = "browser-worker/v1"


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
            mode_ok = resolved.is_file() and not candidate.is_symlink()
            contained = resolved.is_relative_to(self.root)
        except OSError:
            mode_ok = contained = False
        if not mode_ok or not contained:
            route.fulfill(status=404, body=b"not found", content_type="text/plain")
            return
        mime = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        route.fulfill(status=200, body=resolved.read_bytes(), content_type=mime)


class PageTrafficTransport:
    def __init__(
        self,
        page: Page,
        *,
        runtime_errors: list[str],
        network_violations: list[str],
    ) -> None:
        self.page = page
        self.runtime_errors = runtime_errors
        self.network_violations = network_violations

    def _call(self, method: str, *args: Any) -> Any:
        return self.page.evaluate(
            """async ({method, args}) => {
              const bridge = globalThis.__RALPH_BENCH__;
              if (!bridge || bridge.apiVersion !== "traffic/v1") {
                throw new Error("traffic/v1 bridge is unavailable");
              }
              const fn = bridge[method];
              if (typeof fn !== "function") {
                throw new Error(`traffic/v1 method ${method}() is unavailable`);
              }
              return await fn.apply(bridge, args);
            }""",
            {"method": method, "args": list(args)},
        )

    def describe_network(self) -> Any:
        return self._call("describeNetwork")

    def load_scenario(self, scenario: dict[str, Any]) -> None:
        self._call("loadScenario", scenario)

    def reset(self, seed: int) -> None:
        self._call("reset", seed)

    def advance(self, simulated_milliseconds: int) -> None:
        self._call("advance", simulated_milliseconds)

    def snapshot(self) -> dict[str, Any]:
        value = self._call("snapshot")
        if not isinstance(value, dict):
            raise TypeError("snapshot() must return an object")
        inherited = value.get("runtime_errors", value.get("runtimeErrors", []))
        errors = list(inherited) if isinstance(inherited, list) else [str(inherited)]
        errors.extend(self.runtime_errors)
        errors.extend(f"network-blocked:{item}" for item in self.network_violations)
        value["runtime_errors"] = errors
        return value

    def drain_events(self) -> list[dict[str, Any]]:
        value = self._call("drainEvents")
        if not isinstance(value, list):
            raise TypeError("drainEvents() must return an array")
        return value


def _prepare_page(context: Any, candidate: Path) -> tuple[Page, CandidateRouter, list[str], list[dict[str, str]]]:
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
        lambda message: console.append(
            {"type": message.type, "text": message.text[:2000]}
        ),
    )
    page.goto(f"{_ORIGIN}/index.html", wait_until="domcontentloaded", timeout=10_000)
    return page, router, runtime_errors, console


def _capture(
    browser: Any,
    candidate: Path,
    output: Path,
    scenario: Any,
) -> dict[str, Any]:
    capture_started = time.monotonic()
    video_root = output / ".video"
    video_root.mkdir()
    context = browser.new_context(
        viewport=_VIEWPORT,
        record_video_dir=str(video_root),
        record_video_size=_VIEWPORT,
        service_workers="block",
        offline=True,
    )
    page, router, errors, console = _prepare_page(context, candidate)
    video = page.video
    captured_at_ms: int | None = None
    replay_error: str | None = None
    try:
        transport = PageTrafficTransport(
            page, runtime_errors=errors, network_violations=router.blocked
        )
        transport.load_scenario(scenario.to_dict())
        transport.reset(scenario.seed)
        elapsed = 0
        poster_target = 480_000
        while elapsed < scenario.horizon_ms:
            amount = min(_CAPTURE_STEP_MS, scenario.horizon_ms - elapsed)
            transport.advance(amount)
            elapsed += amount
            page.wait_for_timeout(_CAPTURE_DELAY_MS)
            if captured_at_ms is None and elapsed >= poster_target:
                page.screenshot(path=str(output / "overview.png"), full_page=False)
                captured_at_ms = elapsed
    except Exception as exc:
        replay_error = f"{type(exc).__name__}: {exc}"[:2000]
        page.wait_for_timeout(1_000)
    finally:
        if not (output / "overview.png").exists():
            page.screenshot(path=str(output / "overview.png"), full_page=False)
            captured_at_ms = 0
        context.close()
    if video is None:
        raise WorkerError("Playwright did not create a video artifact")
    video.save_as(str(output / "overview.webm"))
    shutil.rmtree(video_root, ignore_errors=True)
    duration_ms = max(1, round((time.monotonic() - capture_started) * 1_000))
    return {
        "schema_version": "capture/v1",
        "viewport": _VIEWPORT,
        "scenario_id": scenario.scenario_id,
        "scenario_profile": scenario.profile,
        "seed": scenario.seed,
        "simulated_horizon_ms": scenario.horizon_ms,
        "poster_simulation_ms": captured_at_ms,
        "simulation_interval_ms": {
            "start": 0,
            "end": scenario.horizon_ms,
            "step": _CAPTURE_STEP_MS,
        },
        "simulation_phase": "full-scenario-replay",
        "playback_step_ms": _CAPTURE_STEP_MS,
        "playback_delay_ms": _CAPTURE_DELAY_MS,
        "playback_rate": round(_CAPTURE_STEP_MS / _CAPTURE_DELAY_MS, 6),
        "duration_ms": duration_ms,
        "frame_rate_fps": _VIDEO_FRAME_RATE_FPS,
        "capture_worker": {
            "id": "ralph-bench.browser-worker",
            "protocol": _CAPTURE_WORKER_PROTOCOL,
            "version": package_version("ralph-bench"),
        },
        "network_violations": list(router.blocked),
        "runtime_errors": errors,
        "console": console,
        "replay_error": replay_error,
    }


def run_worker(candidate: Path, output: Path, chromium: Path, seed: int) -> dict[str, Any]:
    if not candidate.is_dir() or candidate.is_symlink():
        raise WorkerError("candidate must be a real directory")
    if output.exists():
        raise WorkerError("browser output directory already exists")
    output.mkdir(parents=True)
    scenario = build_balanced_scenario(seed)
    expected_network = busy_intersection_network()
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
        evaluation_context = browser.new_context(
            viewport=_VIEWPORT,
            service_workers="block",
            offline=True,
        )
        page, router, errors, console = _prepare_page(evaluation_context, candidate)
        transport = PageTrafficTransport(
            page, runtime_errors=errors, network_violations=router.blocked
        )
        described_network: object | None = None
        described_network_error: str | None = None
        candidate_network: NetworkDescription | None = None
        try:
            described_network = transport.describe_network()
            candidate_network = NetworkDescription.from_dict(described_network)
        except Exception as exc:
            described_network_error = f"{type(exc).__name__}: {exc}"[:2000]
            errors.append(f"describeNetwork:{described_network_error}")
        evaluation = evaluate_transport(
            transport,
            scenario,
            expected_network,
            step_ms=1_000,
            candidate_network=candidate_network,
            candidate_network_error=described_network_error,
        )
        evaluation_context.close()
        capture = _capture(browser, candidate, output, scenario)
        browser.close()
    capture.update(
        {
            "browser": "chromium",
            "browser_version": browser_version,
            "playwright_version": package_version("playwright"),
        }
    )
    result = {
        "schema_version": "browser-evaluation/v1",
        "evaluation": evaluation.to_dict(),
        "scenario": scenario.to_dict(),
        "expected_network": expected_network.to_dict(),
        "described_network": described_network,
        "described_network_error": described_network_error,
        "browser": {
            "name": "chromium",
            "version": browser_version,
            "playwright_version": package_version("playwright"),
            "executable": chromium.name,
            "console": console,
            "page_errors": errors,
            "network_violations": list(router.blocked),
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
    args = parser.parse_args(argv)
    try:
        run_worker(args.candidate, args.output, args.chromium, args.seed)
    except Exception as exc:
        # stdout/stderr belong to the conductor's raw evidence.  Do not emit a
        # traceback containing arbitrary candidate values by default.
        print(f"browser worker failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
