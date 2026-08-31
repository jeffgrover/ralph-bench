"""Deterministic, read-only static reporting over validated bundles."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable

from .bundles import BundleError, BundleValidationResult, safe_extract_bundle, validate_bundle


class ReportBuildError(RuntimeError):
    """The report destination or bundle source cannot be processed safely."""


@dataclass(frozen=True, slots=True)
class BuildResult:
    output: Path
    valid_bundle_count: int
    invalid_bundle_count: int
    run_ids: tuple[str, ...]


_CSS = """
:root {
  color-scheme: dark;
  --bg: #0b1020;
  --panel: #121a2e;
  --panel-2: #18233d;
  --line: #2a385b;
  --text: #edf2ff;
  --muted: #9aa9ca;
  --green: #62e6a7;
  --amber: #ffd166;
  --red: #ff7d8d;
  --blue: #7da9ff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: radial-gradient(circle at top right, #1c2b50 0, var(--bg) 42rem);
  color: var(--text);
  font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
}
a { color: var(--blue); }
main { max-width: 1180px; margin: 0 auto; padding: 48px 28px 72px; }
.eyebrow { color: var(--green); font-size: 12px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }
h1 { margin: 8px 0; font-size: clamp(32px, 6vw, 64px); line-height: .98; letter-spacing: -.04em; }
h2 { margin-top: 44px; font-size: 22px; }
.lede { max-width: 720px; color: var(--muted); font-size: 17px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 28px 0; }
.card, .run, .callout { background: color-mix(in srgb, var(--panel) 90%, transparent); border: 1px solid var(--line); border-radius: 16px; padding: 18px; }
.card .value { display: block; font-size: 30px; font-weight: 800; }
.card .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .1em; }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 16px; }
table { width: 100%; border-collapse: collapse; min-width: 760px; }
th, td { padding: 14px 16px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { color: var(--muted); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }
tr:last-child td { border-bottom: 0; }
.status { font-weight: 800; }
.status.pass { color: var(--green); }
.status.fail { color: var(--red); }
.status.experimental { color: var(--amber); }
.muted { color: var(--muted); }
.callout { color: var(--muted); margin: 22px 0; }
.callout strong { color: var(--text); }
.run-header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; flex-wrap: wrap; }
.run-header .status { font-size: 18px; }
.media { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; margin: 24px 0; }
.media img { display: block; width: 100%; border: 1px solid var(--line); border-radius: 12px; }
.media video { width: 100%; border: 1px solid var(--line); border-radius: 12px; background: #000; }
pre { overflow-x: auto; background: #080c18; border: 1px solid var(--line); border-radius: 12px; padding: 16px; color: #c8d5f5; }
@media (max-width: 700px) { main { padding: 32px 16px 56px; } .media { grid-template-columns: 1fr; } }
""".strip() + "\n"


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReportBuildError(f"bundle document is unreadable: {path}") from exc


def _text(value: Any, default: str = "—") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _number(value: Any, default: int | float | None = None) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return value


def _safe_run_directory(run_id: str, digest: str, used: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", run_id.casefold()).strip("-") or "run"
    candidate = f"{slug[:48]}-{digest[:12]}"
    if candidate in used:
        raise ReportBuildError(f"run directory collision for {run_id!r}")
    used.add(candidate)
    return candidate


def _read_run_record(extracted: Path, bundle: Path, validation: BundleValidationResult) -> dict[str, Any]:
    run = _json(extracted / "run.json")
    experiment = _json(extracted / "experiment.json")
    metrics = _json(extracted / "metrics.json")
    cost = _json(extracted / "cost.json")
    challenge = _json(extracted / "challenge.json")
    assertions = _json(extracted / "evaluation" / "assertions.json")
    isolation = _json(extracted / "provenance" / "isolation.json")
    configuration = _json(extracted / "provenance" / "configuration.json")
    preflight_path = extracted / "provenance" / "toolchain-preflight.json"
    preflight = _json(preflight_path) if preflight_path.is_file() else {}
    if not isinstance(run, dict) or not isinstance(experiment, dict) or not isinstance(metrics, dict):
        raise ReportBuildError(f"bundle has invalid report documents: {bundle}")
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    return {
        "run_id": _text(run.get("run_id"), validation.run_id or "unknown"),
        "bundle_sha256": digest,
        "bundle_name": bundle.name,
        "challenge": _text(run.get("challenge")),
        "scenario_pack": _text(run.get("scenario_pack")),
        "outcome": _text(run.get("outcome"), "failed"),
        "simulation_outcome": _text(run.get("simulation_outcome"), "failed"),
        "measurement_status": _text(run.get("measurement_status"), "unmeasurable"),
        "performance_eligible": bool(run.get("performance_eligible", False)),
        "public_conformance": (
            run.get("public_conformance")
            if isinstance(run.get("public_conformance"), dict)
            else {}
        ),
        "public_accepted": bool(run.get("public_accepted")),
        "attempt_count": _number(run.get("attempt_count"), 0),
        "repetition": _number(run.get("repetition"), 0),
        "track": _text(experiment.get("track")),
        "client": _text(experiment.get("client")),
        "provider": _text(experiment.get("provider")),
        "model": _text(experiment.get("model")),
        "metrics": metrics,
        "cost": cost if isinstance(cost, dict) else {},
        "assertions": assertions if isinstance(assertions, dict) else {},
        "isolation": isolation if isinstance(isolation, dict) else {},
        "configuration": configuration if isinstance(configuration, dict) else {},
        "preflight": preflight if isinstance(preflight, dict) else {},
    }


def _copy_file(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise ReportBuildError(f"validated bundle file is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _copy_run_assets(extracted: Path, destination: Path) -> None:
    _copy_file(extracted / "captures" / "overview.png", destination / "overview.png")
    _copy_file(extracted / "captures" / "overview.webm", destination / "overview.webm")
    artifact = extracted / "artifact" / "submission"
    if artifact.is_dir() and not artifact.is_symlink():
        shutil.copytree(artifact, destination / "artifact", symlinks=False)


def _render_index(records: list[dict[str, Any]]) -> str:
    passed = sum(item["outcome"] == "passed" for item in records)
    local = sum(item["track"] == "local" for item in records)
    cloud = sum(item["track"] != "local" for item in records)
    rows = []
    for item in records:
        status_class = "pass" if item["outcome"] == "passed" else "fail"
        run_dir = item["report_directory"]
        simulation = item["metrics"].get("simulation", {})
        peak = _number(simulation.get("peak_monitored_throughput")) if isinstance(simulation, dict) else None
        rows.append(
            "<tr>"
            f"<td><a href=\"runs/{html.escape(run_dir)}/index.html\">{html.escape(item['run_id'])}</a><br>"
            f"<span class=\"muted\">{html.escape(item['model'])}</span></td>"
            f"<td>{html.escape(item['client'])} × {html.escape(item['provider'])}<br>"
            f"<span class=\"muted\">{html.escape(item['track'])}</span></td>"
            f"<td class=\"status {status_class}\">{html.escape(item['outcome'])}</td>"
            f"<td>{html.escape(item['measurement_status'])}<br>"
            f"<span class=\"muted\">peak {html.escape(str(peak if peak is not None else '—'))}/min</span></td>"
            f"<td>{html.escape(str(item['attempt_count']))}</td>"
            "</tr>"
        )
    body = "".join(rows) or '<tr><td colspan="5" class="muted">No valid bundles found.</td></tr>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ralph Bench — results</title><link rel="stylesheet" href="assets/site.css"></head>
<body><main><div class="eyebrow">Ralph Bench / immutable evidence</div>
<h1>Working systems first.</h1>
<p class="lede">A read-only view over validated runs. Functional acceptance is the admission floor; traffic performance, agent efficiency, and visual quality remain separate dimensions.</p>
<div class="grid">
<div class="card"><span class="value">{len(records)}</span><span class="label">valid runs</span></div>
<div class="card"><span class="value">{passed}</span><span class="label">full passes</span></div>
<div class="card"><span class="value">{local}</span><span class="label">local track</span></div>
<div class="card"><span class="value">{cloud}</span><span class="label">cloud tracks</span></div>
</div>
<div class="callout"><strong>Interpretation.</strong> A failure remains visible and navigable when it reached evaluation. Performance comparisons belong only to sufficiently evidenced, functionally eligible artifacts.</div>
<h2>Runs</h2><div class="table-wrap"><table><thead><tr><th>Run / model</th><th>Composition</th><th>Outcome</th><th>Measurement</th><th>Attempts</th></tr></thead><tbody>{body}</tbody></table></div>
<p class="muted">Generated deterministically from validated .ralph.zip bundles. Candidate artifacts are offered as explicit downloads; they are never executed by this report.</p>
</main></body></html>
"""


def _render_run(record: dict[str, Any]) -> str:
    status_class = "pass" if record["outcome"] == "passed" else "fail"
    simulation = record["metrics"].get("simulation", {})
    agent = record["metrics"].get("agent", {})
    assertions = record["assertions"].get("assertions", [])
    assertion_rows = []
    if isinstance(assertions, list):
        for assertion in assertions:
            if not isinstance(assertion, dict):
                continue
            result = _text(assertion.get("result"), "unknown")
            assertion_rows.append(
                f"<tr><td>{html.escape(_text(assertion.get('assertion_id')))}</td>"
                f"<td class=\"status {'pass' if result == 'pass' else 'fail'}\">{html.escape(result)}</td>"
                f"<td>{html.escape(_text(assertion.get('detail')))}</td></tr>"
            )
    assertion_body = "".join(assertion_rows) or '<tr><td colspan="3" class="muted">No assertion records.</td></tr>'
    metrics_text = json.dumps(record["metrics"], ensure_ascii=False, sort_keys=True, indent=2)
    cost_text = json.dumps(record["cost"], ensure_ascii=False, sort_keys=True, indent=2)
    public_conformance = record.get("public_conformance", {})
    public_status = (
        public_conformance.get("outcome", "unavailable")
        if isinstance(public_conformance, dict)
        else "unavailable"
    )
    artifact_link = (
        '<a download href="artifact/index.html">download candidate entrypoint</a>'
        if record.get("artifact_available")
        else '<span class="muted">candidate entrypoint unavailable</span>'
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ralph Bench — {html.escape(record['run_id'])}</title><link rel="stylesheet" href="../../assets/site.css"></head>
<body><main><p><a href="../../index.html">← all runs</a></p>
<div class="run-header"><div><div class="eyebrow">{html.escape(record['challenge'])}</div><h1>{html.escape(record['run_id'])}</h1><p class="lede">{html.escape(record['model'])} through {html.escape(record['client'])} × {html.escape(record['provider'])} on the {html.escape(record['track'])} track.</p></div><div class="status {status_class}">{html.escape(record['outcome'])}</div></div>
<div class="grid"><div class="card"><span class="value">{html.escape(str(record['attempt_count']))}</span><span class="label">attempts</span></div>
<div class="card"><span class="value">{html.escape(str(_number(simulation.get('peak_monitored_throughput'), '—') if isinstance(simulation, dict) else '—'))}</span><span class="label">peak vehicles/min</span></div>
<div class="card"><span class="value">{html.escape(str(_number(agent.get('wall_seconds'), '—') if isinstance(agent, dict) else '—'))}</span><span class="label">agent seconds</span></div>
<div class="card"><span class="value">{html.escape(str(_number(agent.get('usage', {}).get('total_tokens'), '—') if isinstance(agent, dict) and isinstance(agent.get('usage'), dict) else '—'))}</span><span class="label">reported tokens</span></div>
<div class="card"><span class="value">{html.escape(record['measurement_status'])}</span><span class="label">measurement</span></div></div>
<div class="callout"><strong>Performance eligibility:</strong> {"eligible for the performance vector" if record["performance_eligible"] else "not eligible for performance comparison"}. This is independent of the overall pass/fail outcome.</div>
<div class="callout"><strong>Public conformance:</strong> {html.escape(str(public_status))}. The staged public smoke result is preserved separately from the private scored profile.</div>
<div class="callout"><strong>Isolation:</strong> {html.escape(_text(record['isolation'].get('level'), 'L0/unsealed'))}. <strong>Preflight:</strong> {html.escape(_text(record['preflight'].get('status'), 'not recorded'))}. Configuration and toolchain provenance remain in the bundle.</div>
<div class="media"><div><h2>Recorded poster</h2><img src="overview.png" alt="Evaluator-recorded simulation poster"></div><div><h2>Recorded overview</h2><video controls preload="metadata" src="overview.webm"></video></div></div>
<h2>Acceptance assertions</h2><div class="table-wrap"><table><thead><tr><th>Assertion</th><th>Result</th><th>Observed evidence</th></tr></thead><tbody>{assertion_body}</tbody></table></div>
<h2>Evidence</h2><div class="callout"><strong>Artifact:</strong> {artifact_link}. This report does not execute candidate HTML or JavaScript.</div>
<pre>{html.escape(metrics_text)}</pre><h2>Cost evidence</h2><pre>{html.escape(cost_text)}</pre>
<p class="muted">Bundle: {html.escape(record['bundle_name'])}<br>SHA-256: {html.escape(record['bundle_sha256'])}</p>
</main></body></html>
"""


def _bundle_paths(inbox: Path) -> Iterable[Path]:
    if not inbox.is_dir() or inbox.is_symlink():
        return ()
    return tuple(
        path
        for path in sorted(inbox.iterdir(), key=lambda item: item.name)
        if path.is_file() and not path.is_symlink() and path.name.endswith(".ralph.zip")
    )


def build_site(inbox: Path, output: Path) -> BuildResult:
    """Build a fresh static site without modifying source bundles."""

    inbox = Path(inbox).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ReportBuildError(
            f"report output already exists; choose a new directory or remove it explicitly: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    records: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    used_directories: set[str] = set()
    try:
        (temporary / "assets").mkdir(parents=True)
        (temporary / "assets" / "site.css").write_text(_CSS, encoding="utf-8")
        for bundle in _bundle_paths(inbox):
            validation = validate_bundle(bundle)
            if not validation.valid:
                invalid.append(
                    {
                        "path": bundle.name,
                        "diagnostics": [
                            {
                                "code": item.code,
                                "path": item.path,
                                "detail": item.detail,
                            }
                            for item in validation.diagnostics
                        ],
                    }
                )
                continue
            with tempfile.TemporaryDirectory(prefix="ralph-report-extract-") as extracted_name:
                try:
                    extracted = safe_extract_bundle(
                        bundle, Path(extracted_name) / "bundle"
                    ).path
                except BundleError as exc:
                    raise ReportBuildError(
                        f"validated bundle could not be extracted: {bundle.name}"
                    ) from exc
                record = _read_run_record(extracted, bundle, validation)
                directory = _safe_run_directory(record["run_id"], record["bundle_sha256"], used_directories)
                record["report_directory"] = directory
                record["artifact_available"] = (
                    extracted / "artifact" / "submission" / "index.html"
                ).is_file()
                destination = temporary / "runs" / directory
                destination.mkdir(parents=True)
                _copy_run_assets(extracted, destination)
                (destination / "index.html").write_text(_render_run(record), encoding="utf-8")
                records.append(record)
        records.sort(key=lambda item: (item["track"], item["model"], item["run_id"]))
        (temporary / "data").mkdir()
        (temporary / "data" / "catalog.json").write_text(
            json.dumps(records, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        (temporary / "data" / "invalid-bundles.json").write_text(
            json.dumps(invalid, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        (temporary / "build-manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "report-build/v1",
                    "source": "bundle-inbox",
                    "valid_bundle_count": len(records),
                    "invalid_bundle_count": len(invalid),
                    "run_ids": [item["run_id"] for item in records],
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (temporary / "index.html").write_text(_render_index(records), encoding="utf-8")
        temporary.rename(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return BuildResult(output, len(records), len(invalid), tuple(item["run_id"] for item in records))


__all__ = ["BuildResult", "ReportBuildError", "build_site"]
