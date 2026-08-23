"""The ``rb`` command and an injectable client-first authoring wizard."""

from __future__ import annotations

import argparse
from dataclasses import replace
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import sys
from typing import Callable, Sequence

from .adapters import AdapterRegistry, built_in_registry, resolve_sut
from .adapters.contracts import ProbeContext, ProbeResult
from .adapters.resolver import ResolutionError
from .bundles import validate_bundle
from .experiments import (
    ExperimentError,
    load_experiment,
    parse_experiment,
    render_experiment,
    save_experiment,
)


class WizardCancelled(Exception):
    """The operator cancelled authoring before a file was created."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rb", description="Ralph Bench")
    sub = parser.add_subparsers(dest="command")
    configure = sub.add_parser("configure", help="author and validate an experiment")
    configure.add_argument("path", nargs="?", type=Path)
    run = sub.add_parser("run", help="validate an experiment and prepare execution")
    run.add_argument("path", type=Path)
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

    def _ask_decimal(self, prompt: str) -> Decimal:
        answer = self._ask(prompt)
        try:
            value = Decimal(answer)
        except (InvalidOperation, ValueError) as exc:
            raise ExperimentError(f"{prompt} must be a decimal") from exc
        if not value.is_finite():
            raise ExperimentError(f"{prompt} must be finite")
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
            self.output(f"  {index}. {label} ({identifier})")
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

            name = self._ask(
                "Experiment name", "codex-chatgpt-luna-intersection"
            )
            challenge = self._ask("Challenge", "busy-intersection/v1")
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
            repetitions = self._ask_positive_int("Repetitions", 1)
            max_wall_seconds = self._ask_positive_int(
                "Maximum wall seconds per run", 1200
            )
            max_attempts = self._ask_positive_int("Maximum attempts", 2)
            scenario_pack = self._ask(
                "Evaluation scenario pack", "traffic-intersection-p0a"
            )
            inbox = self._ask("Result inbox", "results/inbox")

            self.output(
                "Subscription cost policy (all financial values are explicit operator inputs):"
            )
            period_cost = self._ask_decimal("  Billing-period cost USD")
            allocation_fraction = self._ask_decimal(
                "  Benchmark allocation fraction (0 through 1)"
            )
            if period_cost < 0:
                raise ExperimentError("billing-period cost cannot be negative")
            if allocation_fraction < 0 or allocation_fraction > 1:
                raise ExperimentError("benchmark allocation fraction must be between 0 and 1")
            computed_pool = (period_cost * allocation_fraction).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            self.output(
                "  Computed experiment pool: "
                f"${format(computed_pool, 'f')} = ${format(period_cost, 'f')} "
                f"× {format(allocation_fraction, 'f')}"
            )
            pool_cost = self._ask(
                "  Resulting experiment pool cost USD", format(computed_pool, "f")
            )
            cost: dict[str, object] = {
                "policy": "flat-subscription-attempt-pool/v1",
                "pool_id": self._ask("  Pool ID", f"{name}-pool"),
                "pool_scope": "experiment",
                "currency": "USD",
                "service_plan": self._ask("  Service plan"),
                "billing_period_cost_usd": format(period_cost, "f"),
                "benchmark_allocation_fraction": format(allocation_fraction, "f"),
                "pool_cost_usd": pool_cost,
                "pool_cost_source": self._ask(
                    "  Pool cost source", "operator_attested_period_charge"
                ),
                "allocation_rationale": self._ask(
                    "  Allocation rationale", "dedicated_benchmark_period"
                ),
                "billing_period_start": self._ask(
                    "  Billing period start (YYYY-MM-DD)"
                ),
                "billing_period_end": self._ask(
                    "  Billing period end (YYYY-MM-DD)"
                ),
                "closure": "all_expected_runs_terminal",
            }
            try:
                entered_pool = Decimal(pool_cost)
            except InvalidOperation:
                entered_pool = Decimal("NaN")
            if entered_pool.is_finite() and entered_pool == 0:
                cost["zero_cost_evidence"] = self._ask("  Zero-cost plan evidence")

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
                "track": "cloud-subscription",
                "repetitions": repetitions,
                "client_options": client_options,
                "budget": {
                    "max_wall_seconds": max_wall_seconds,
                    "max_attempts": max_attempts,
                },
                "evaluation": {"scenario_pack": scenario_pack},
                "cost": cost,
                "output": {"inbox": inbox},
            }
            experiment = parse_experiment(raw)
            self.output(
                f"  Cost review: period ${experiment.cost.billing_period_cost_usd}, "
                f"fraction {experiment.cost.benchmark_allocation_fraction}, "
                f"pool ${experiment.cost.pool_cost_usd}"
            )
            self.output("Experiment review:")
            self.output(render_experiment(experiment))
            confirmation = self._ask("Save this experiment? (yes/no)", "yes")
            if confirmation.lower() not in {"y", "yes"}:
                raise WizardCancelled
            path = destination or Path(
                self._ask("Save path", "experiments/experiment.toml")
            )
            save_experiment(experiment, path)
        except WizardCancelled:
            self.output("Authoring cancelled; no experiment file was written.")
            return 130
        except (ExperimentError, ResolutionError, OSError, KeyError, ValueError) as exc:
            self.output(f"Invalid experiment; no experiment file was written: {exc}")
            return 2
        self.output(f"Saved validated experiment: {path}")
        return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    stdin=None,
    registry: AdapterRegistry | None = None,
    probe_context: ProbeContext | None = None,
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
        return Wizard(
            input_fn,
            output_fn,
            registry=registry,
            probe_context=probe_context,
        ).run()
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
        try:
            experiment = load_experiment(args.path)
            sut = resolve_sut(experiment, registry, context=probe_context)
        except (OSError, ExperimentError, ResolutionError) as exc:
            output_fn(f"Invalid experiment or unavailable SUT: {exc}")
            return 2
        output_fn(
            f"Validated experiment {experiment.name!r} as "
            f"{sut.harness_id} × {sut.provider_id} × {sut.model_id}."
        )
        output_fn(
            "Execution is not implemented in this P0-A CLI slice; "
            "no model invocation was attempted."
        )
        return 3
    if args.command == "doctor":
        harness = registry.get("harness", "codex-cli")
        result = harness.detect(probe_context)
        payload = {
            "client": "codex-cli",
            "status": result.status,
            "available": result.available,
            "message": result.message,
            "version": result.version,
        }
        output_fn(
            json.dumps(payload, sort_keys=True)
            if args.json
            else f"Codex CLI: {result.status} ({result.message})"
        )
        return 0 if result.available else 1
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
