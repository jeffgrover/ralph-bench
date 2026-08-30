"""The ``rb`` command and an injectable client-first authoring wizard."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import re
import sys
from typing import Callable, Sequence

from .adapters import AdapterRegistry, built_in_registry, resolve_sut
from .adapters.contracts import (
    ProbeContext,
    ProbeResult,
    tracks_for_cost_capabilities,
)
from .adapters.resolver import ResolutionError
from .bundles import validate_bundle
from .browser_runtime import (
    BrowserRuntimeError,
    find_chromium,
    find_playwright_browsers_path,
)
from .challenges import challenge_ids_for, scenario_pack_for
from .conductor import ConductorError, EvaluationRunSummary, execute_experiment
from .experiments import (
    ExperimentError,
    load_experiment,
    parse_experiment,
    render_experiment,
    save_experiment,
)
from .preview import PreviewError, open_bundle_preview


class WizardCancelled(Exception):
    """The operator cancelled authoring before a file was created."""


def _default_experiment_path(name: str) -> Path:
    """Derive a safe, legible project-local filename from an experiment name."""

    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return Path("experiments") / f"{slug or 'experiment'}.toml"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rb", description="Ralph Bench")
    sub = parser.add_subparsers(dest="command")
    configure = sub.add_parser("configure", help="author and validate an experiment")
    configure.add_argument("path", nargs="?", type=Path)
    run = sub.add_parser("run", help="execute a validated experiment")
    run.add_argument("path", type=Path)
    preview = sub.add_parser(
        "preview", help="open a bundle's evaluator-recorded simulation overview"
    )
    preview.add_argument("path", type=Path)
    doctor = sub.add_parser("doctor", help="perform read-only adapter diagnostics")
    doctor.add_argument("--json", action="store_true", help="emit machine-readable diagnostics")
    bundle = sub.add_parser("bundle", help="inspect immutable result bundles")
    bundle_subcommands = bundle.add_subparsers(dest="bundle_command", required=True)
    bundle_validate = bundle_subcommands.add_parser(
        "validate", help="validate one .ralph.zip bundle without extracting it"
    )
    bundle_validate.add_argument("path", type=Path)
    bundle_validate.add_argument(
        "--json", action="store_true", help="emit machine-readable diagnostics"
    )
    build = sub.add_parser("build", help="build the static result site")
    build.add_argument(
        "--source", type=Path, default=Path("results/inbox"), dest="inbox"
    )
    build.add_argument("--output", type=Path, default=Path("site"))
    return parser


class Wizard:
    """Small state engine whose choices come from the adapter registry."""

    def __init__(
        self,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
        *,
        registry: AdapterRegistry | None = None,
        probe_context: ProbeContext | None = None,
    ) -> None:
        self.input = input_fn
        self.output = output_fn
        self.registry = registry or built_in_registry()
        self.probe_context = probe_context or ProbeContext()
        self.saved_path: Path | None = None
        self.saved_experiment = None

    def _ask(self, prompt: str, default: str | None = None) -> str:
        suffix = f" [{default}]" if default is not None else ""
        try:
            answer = self.input(f"{prompt}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise WizardCancelled from exc
        if answer.lower() in {"q", "quit", "cancel"}:
            raise WizardCancelled
        return answer or (default or "")

    def _ask_positive_int(self, prompt: str, default: int) -> int:
        answer = self._ask(prompt, str(default))
        try:
            value = int(answer)
        except ValueError as exc:
            raise ExperimentError(f"{prompt} must be an integer") from exc
        if value < 1:
            raise ExperimentError(f"{prompt} must be positive")
        return value

    def _ask_repair_passes(self, default: int = 1) -> int:
        """Ask for the permitted controlled Ralph repairs per run."""
        prompt = "Ralph repair passes per independent run"
        answer = self._ask(prompt, str(default))
        try:
            value = int(answer)
        except ValueError as exc:
            raise ExperimentError(f"{prompt} must be an integer") from exc
        if value < 0:
            raise ExperimentError(f"{prompt} cannot be negative")
        if value > 1:
            raise ExperimentError(f"{prompt} cannot exceed 1 in P0-A")
        return value

    def _select(
        self,
        title: str,
        values: list[tuple[str, str]],
        default: str | None = None,
        *,
        allow_manual: bool = False,
    ) -> str:
        self.output(title)
        for index, (identifier, label) in enumerate(values, 1):
            display = label if label == identifier else f"{label} ({identifier})"
            self.output(f"  {index}. {display}")
        if not values:
            if allow_manual:
                return self._ask("  Manual value")
            raise ExperimentError(f"no compatible {title.rstrip(':').lower()} is registered")
        choice = self._ask("  Select number or identifier", default or values[0][0])
        if choice.isdigit() and 1 <= int(choice) <= len(values):
            return values[int(choice) - 1][0]
        if choice in {identifier for identifier, _ in values}:
            return choice
        if allow_manual:
            self.output("  Continuing with the manually entered identifier.")
            return choice
        raise ExperimentError(
            "choose one of the registered identifiers; an executable path can "
            "be entered after selecting the client"
        )

    def _client_choices(self) -> tuple[list[tuple[str, str]], dict[str, ProbeResult]]:
        choices: list[tuple[str, str]] = []
        probes: dict[str, ProbeResult] = {}
        for adapter in self.registry.harnesses.values():
            identifier = adapter.descriptor.adapter_id.removeprefix("harness/")
            probe = adapter.detect(self.probe_context)
            probes[identifier] = probe
            executable = probe.evidence.get(
                "executable", getattr(adapter, "executable", identifier)
            )
            details = [probe.status, f"executable {executable}"]
            if probe.version is not None:
                details.append(f"version {probe.version}")
            choices.append(
                (
                    identifier,
                    f"{adapter.descriptor.label} — {', '.join(details)}",
                )
            )
        return choices, probes

    def run(self, destination: Path | None = None) -> int:
        self.saved_path = None
        self.saved_experiment = None
        try:
            harness_values, harness_probes = self._client_choices()
            default_client = next(
                (
                    identifier
                    for identifier, _label in harness_values
                    if harness_probes[identifier].available
                ),
                harness_values[0][0] if harness_values else None,
            )
            client = self._select(
                "Client (read-only detection results):",
                harness_values,
                default_client,
            )
            harness = self.registry.get("harness", client)
            detection = harness_probes.get(client) or harness.detect(self.probe_context)
            active_context = self.probe_context
            if not detection.available:
                executable = self._ask(
                    "Client executable path",
                    str(getattr(harness, "executable", client)),
                )
                active_context = replace(self.probe_context, executable=executable)
                detection = harness.detect(active_context)
            self.output(f"  Detection: {detection.status} — {detection.message}")
            if not detection.available:
                raise ExperimentError("the selected client is not available")

            provider_values = [
                (
                    adapter.descriptor.adapter_id.removeprefix("provider/"),
                    adapter.descriptor.label,
                )
                for adapter in self.registry.providers.values()
                if set(harness.connection_requirements()).issubset(
                    set(adapter.descriptor.capabilities)
                )
            ]
            provider = self._select(
                "Provider (compatible with selected client):", provider_values
            )
            provider_adapter = self.registry.get("provider", provider)
            connection = harness.connection_probe(active_context)
            if not connection.available:
                raise ExperimentError(connection.message or "client connection is unavailable")
            provider_context = replace(
                active_context,
                metadata={
                    **active_context.metadata,
                    "credential_available": connection.credential_available,
                },
            )
            provider_probe = provider_adapter.detect(provider_context)
            self.output(
                f"  Provider probe: {provider_probe.status} — {provider_probe.message}"
            )
            if not provider_probe.available:
                raise ExperimentError(provider_probe.message or "provider is unavailable")
            cost_capabilities = provider_adapter.cost_capabilities()
            advertised_tracks = tracks_for_cost_capabilities(cost_capabilities)
            p0_tracks = tuple(
                track
                for track in advertised_tracks
                if track in {"cloud-subscription", "local"}
            )
            if not p0_tracks:
                raise ExperimentError(
                    "selected provider does not advertise a P0-A-compatible "
                    "billing track"
                )
            track = (
                p0_tracks[0]
                if len(p0_tracks) == 1
                else self._select(
                    "Execution track:",
                    [(value, value) for value in p0_tracks],
                )
            )
            offers = provider_adapter.discover_models(provider_context)
            model_values = [
                (
                    offer.provider_model_id,
                    f"{offer.label} — {offer.source}, {offer.freshness}",
                )
                for offer in offers
            ]
            model = self._select(
                "Model (provider offers; manual entry is allowed):",
                model_values,
                allow_manual=True,
            )
            selected_offer = next(
                (offer for offer in offers if offer.provider_model_id == model), None
            )
            model_adapter = next(
                (
                    adapter
                    for adapter in self.registry.models.values()
                    if selected_offer is not None
                    and adapter.descriptor.adapter_id != "model/generic"
                    and adapter.match(selected_offer)
                ),
                self.registry.get("model", "model/generic"),
            )

            name = self._ask("Experiment name", "codex-luna")
            challenge_ids = challenge_ids_for(track)
            challenge = self._select(
                "Challenge:",
                [(value, value) for value in challenge_ids],
                "busy-intersection/v1"
                if "busy-intersection/v1" in challenge_ids
                else None,
            )
            scenario_pack = scenario_pack_for(challenge, track)
            self.output(
                f"  Evaluation profile: {scenario_pack} "
                "(derived from challenge and execution track)"
            )
            effort_schema = model_adapter.option_schema().get("reasoning_effort", {})
            effort_values = (
                effort_schema.get("values", ())
                if isinstance(effort_schema, dict)
                else ()
            )
            effort = (
                self._select(
                    "Reasoning effort:",
                    [(str(value), str(value)) for value in effort_values],
                    "medium" if "medium" in effort_values else None,
                )
                if effort_values
                else self._ask("Reasoning effort", "medium")
            )
            repetitions = self._ask_positive_int(
                "Independent runs per configuration "
                "(aggregate results and measure variability)",
                1,
            )
            max_wall_seconds = self._ask_positive_int(
                "Maximum model-work time per independent run, shared by the "
                "initial attempt and repair (seconds)",
                1200,
            )
            repair_passes = self._ask_repair_passes()
            # The persisted budget counts the initial attempt as well as each
            # controlled repair pass. Keep that schema meaning out of the
            # authoring prompt so operators can reason in Ralph terms.
            max_attempts = repair_passes + 1
            inbox = self._ask("Result inbox", "results/inbox")

            client_options: dict[str, object] = {
                "reasoning_effort": effort,
                "loop": "controlled",
            }
            if active_context.executable is not None:
                client_options["executable"] = active_context.executable
            raw: dict[str, object] = {
                "schema_version": "experiment/v1",
                "name": name,
                "challenge": challenge,
                "client": client,
                "provider": provider,
                "model": model,
                "track": track,
                "repetitions": repetitions,
                "client_options": client_options,
                "budget": {
                    "max_wall_seconds": max_wall_seconds,
                    "max_attempts": max_attempts,
                },
                "evaluation": {"scenario_pack": scenario_pack},
                "output": {"inbox": inbox},
            }
            experiment = parse_experiment(raw)
            if track == "local":
                self.output("  Cost: not applicable — local execution track")
            elif "unavailable" in cost_capabilities.evidence_statuses:
                self.output("  Cost: subscription — per-run USD unavailable")
            else:
                self.output("  Cost: captured from run-side provider evidence")
            self.output("Experiment review:")
            self.output(render_experiment(experiment))
            path = destination or Path(
                self._ask(
                    "Experiment file (enter path to save, or cancel)",
                    str(_default_experiment_path(name)),
                )
            )
            save_experiment(experiment, path)
        except WizardCancelled:
            self.output("Authoring cancelled; no experiment file was written.")
            return 130
        except (ExperimentError, ResolutionError, OSError, KeyError, ValueError) as exc:
            self.output(f"Invalid experiment; no experiment file was written: {exc}")
            return 2
        self.output(f"Saved validated experiment: {path}")
        self.saved_path = path
        self.saved_experiment = experiment
        return 0


def _confirm_run(
    experiment,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> bool | None:
    maximum = experiment.repetitions * experiment.budget.max_attempts
    prompt = (
        "Run this evaluation now? "
        f"({experiment.repetitions} independent run(s), up to "
        f"{maximum} model invocation(s)) (yes/no) [yes]: "
    )
    while True:
        try:
            answer = input_fn(prompt).strip().casefold()
        except (EOFError, KeyboardInterrupt):
            output_fn("Evaluation was not started; the experiment file remains saved.")
            return None
        if answer in {"", "y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        output_fn("Please answer yes or no.")


def _confirm_preview(
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> bool:
    prompt = (
        "Open the final run's recorded simulation overview? "
        "(yes/no) [yes]: "
    )
    while True:
        try:
            answer = input_fn(prompt).strip().casefold()
        except (EOFError, KeyboardInterrupt):
            output_fn("Recorded overview was not opened.")
            return False
        if answer in {"", "y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        output_fn("Please answer yes or no.")


def _run_experiment_path(
    path: Path,
    *,
    registry: AdapterRegistry,
    probe_context: ProbeContext,
    output_fn: Callable[[str], None],
    input_stream=None,
    input_fn: Callable[[str], str] = input,
    evaluation_runner: Callable[..., EvaluationRunSummary] | None = None,
) -> int:
    try:
        experiment = load_experiment(path)
        sut = resolve_sut(experiment, registry, context=probe_context)
    except (OSError, ExperimentError, ResolutionError) as exc:
        output_fn(f"Invalid experiment or unavailable SUT: {exc}")
        return 2
    output_fn(
        f"Validated experiment {experiment.name!r} as "
        f"{sut.harness_id} × {sut.provider_id} × {sut.model_id}."
    )
    runner = evaluation_runner or execute_experiment
    try:
        if evaluation_runner is None:
            summary = runner(
                experiment,
                sut,
                registry,
                output_fn=output_fn,
                input_stream=input_stream,
                probe_context=probe_context,
            )
        else:
            summary = runner(
                experiment,
                sut,
                registry,
                output_fn=output_fn,
            )
    except KeyboardInterrupt:
        output_fn("Evaluation interrupted; active child processes were terminated.")
        return 130
    except (ConductorError, OSError, RuntimeError, ValueError) as exc:
        output_fn(f"Evaluation infrastructure failed: {exc}")
        return 3
    output_fn(
        f"Produced {len(summary.runs)} validated result bundle(s); "
        f"{summary.passed} full pass(es)."
    )
    if (
        summary.runs
        and input_stream is not None
        and getattr(input_stream, "isatty", lambda: False)()
        and _confirm_preview(input_fn, output_fn)
    ):
        try:
            preview = open_bundle_preview(summary.runs[-1].bundle)
        except PreviewError as exc:
            output_fn(f"Could not open recorded overview: {exc}")
        else:
            output_fn(f"Opened recorded simulation overview: {preview.media_path}")
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    stdin=None,
    registry: AdapterRegistry | None = None,
    probe_context: ProbeContext | None = None,
    evaluation_runner: Callable[..., EvaluationRunSummary] | None = None,
) -> int:
    parser = _parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    stdin = sys.stdin if stdin is None else stdin
    registry = registry or built_in_registry()
    probe_context = probe_context or ProbeContext()
    if args.command is None:
        if not stdin.isatty():
            output_fn(
                "rb with no arguments requires an interactive terminal; "
                "use `rb configure <file>` or `rb run <file>`."
            )
            return 2
        wizard = Wizard(
            input_fn,
            output_fn,
            registry=registry,
            probe_context=probe_context,
        )
        authored = wizard.run()
        if authored != 0:
            return authored
        if wizard.saved_path is None or wizard.saved_experiment is None:
            output_fn("Evaluation was not started because no experiment was saved.")
            return 3
        confirmed = _confirm_run(wizard.saved_experiment, input_fn, output_fn)
        if confirmed is None:
            return 130
        if not confirmed:
            output_fn(
                f"Evaluation was not started; run `rb run {wizard.saved_path}` when ready."
            )
            return 0
        return _run_experiment_path(
            wizard.saved_path,
            registry=registry,
            probe_context=probe_context,
            output_fn=output_fn,
            input_stream=stdin,
            input_fn=input_fn,
            evaluation_runner=evaluation_runner,
        )
    if args.command == "configure":
        if args.path is None:
            if not stdin.isatty():
                output_fn("rb configure requires a path in non-interactive mode.")
                return 2
            return Wizard(
                input_fn,
                output_fn,
                registry=registry,
                probe_context=probe_context,
            ).run()
        if args.path.exists():
            try:
                experiment = load_experiment(args.path)
            except (OSError, ExperimentError) as exc:
                output_fn(f"Invalid experiment: {exc}")
                return 2
            output_fn(render_experiment(experiment))
            return 0
        if not stdin.isatty():
            output_fn("rb configure cannot author a missing file without an interactive terminal.")
            return 2
        return Wizard(
            input_fn,
            output_fn,
            registry=registry,
            probe_context=probe_context,
        ).run(args.path)
    if args.command == "run":
        return _run_experiment_path(
            args.path,
            registry=registry,
            probe_context=probe_context,
            output_fn=output_fn,
            input_stream=stdin,
            input_fn=input_fn,
            evaluation_runner=evaluation_runner,
        )
    if args.command == "preview":
        try:
            preview = open_bundle_preview(args.path)
        except PreviewError as exc:
            output_fn(f"Could not open recorded overview: {exc}")
            return 2
        output_fn(f"Opened recorded simulation overview: {preview.media_path}")
        return 0
    if args.command == "doctor":
        harness = registry.get("harness", "codex-cli")
        result = harness.detect(probe_context)
        dependency_checks: dict[str, dict[str, object]] = {}
        try:
            chromium = find_chromium()
            dependency_checks["chromium"] = {
                "available": True,
                "executable": chromium.name,
            }
        except BrowserRuntimeError as exc:
            dependency_checks["chromium"] = {
                "available": False,
                "message": str(exc),
            }
        try:
            find_playwright_browsers_path()
            dependency_checks["playwright_video"] = {"available": True}
        except BrowserRuntimeError as exc:
            dependency_checks["playwright_video"] = {
                "available": False,
                "message": str(exc),
            }
        available = result.available and all(
            bool(check["available"]) for check in dependency_checks.values()
        )
        payload = {
            "client": "codex-cli",
            "status": "ok" if available else "unavailable",
            "available": available,
            "message": result.message,
            "version": result.version,
            "dependencies": dependency_checks,
        }
        output_fn(
            json.dumps(payload, sort_keys=True)
            if args.json
            else (
                f"Codex CLI: {result.status}; "
                + "; ".join(
                    f"{ {'chromium': 'Chromium', 'playwright_video': 'Playwright video'}[name] }: "
                    f"{'ok' if check['available'] else 'unavailable'}"
                    for name, check in dependency_checks.items()
                )
            )
        )
        return 0 if available else 1
    if args.command == "bundle" and args.bundle_command == "validate":
        result = validate_bundle(args.path)
        payload = {
            "valid": result.valid,
            "path": str(args.path),
            "run_id": result.run_id,
            "entries": len(result.entries),
            "total_size": result.total_size,
            "diagnostics": [
                {"code": item.code, "path": item.path, "detail": item.detail}
                for item in result.diagnostics
            ],
        }
        if args.json:
            output_fn(json.dumps(payload, sort_keys=True))
        elif result.valid:
            output_fn(
                f"Valid bundle for run {result.run_id!r}: "
                f"{len(result.entries)} entries, {result.total_size} bytes"
            )
        else:
            output_fn(f"Invalid bundle: {args.path}")
            for item in result.diagnostics:
                location = f" [{item.path}]" if item.path else ""
                detail = f": {item.detail}" if item.detail else ""
                output_fn(f"  {item.code}{location}{detail}")
        return 0 if result.valid else 1
    if args.command == "build":
        output_fn(
            "Static reporting is not implemented in this P0-A CLI slice; "
            f"no files were read from {args.inbox} or written to {args.output}."
        )
        return 3
    parser.error("unknown command")
    return 2
