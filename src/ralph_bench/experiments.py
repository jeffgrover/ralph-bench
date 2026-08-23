"""Versioned experiment files.

The TOML document is deliberately a narrow boundary.  Unknown keys are
rejected before an experiment can be resolved or run.
"""

from __future__ import annotations

import os
import json
import tempfile
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from .costs import CostValidationError, FlatSubscriptionPoolDeclaration


class ExperimentError(ValueError):
    """An experiment failed syntax, schema, or semantic validation."""


@dataclass(frozen=True)
class ClientOptions:
    reasoning_effort: str = "medium"
    loop: str = "controlled"
    executable: str | None = None


@dataclass(frozen=True)
class Budget:
    max_wall_seconds: int = 1200
    max_attempts: int = 2


@dataclass(frozen=True)
class Evaluation:
    scenario_pack: str = "traffic-intersection-p0a"


@dataclass(frozen=True)
class Cost:
    policy: str
    pool_id: str
    pool_scope: str
    currency: str
    service_plan: str
    billing_period_cost_usd: str
    benchmark_allocation_fraction: str
    pool_cost_usd: str
    pool_cost_source: str
    allocation_rationale: str
    billing_period_start: date
    billing_period_end: date
    closure: str
    rounding: str = "USD-0.01-half-up"
    charge_scope: str = "model_invocation"
    zero_cost_evidence: str | None = None

    def declaration(self) -> FlatSubscriptionPoolDeclaration:
        return FlatSubscriptionPoolDeclaration(
            policy=self.policy,
            pool_id=self.pool_id,
            pool_scope=self.pool_scope,
            currency=self.currency,
            service_plan=self.service_plan,
            billing_period_cost_usd=self.billing_period_cost_usd,
            benchmark_allocation_fraction=self.benchmark_allocation_fraction,
            pool_cost_usd=self.pool_cost_usd,
            pool_cost_source=self.pool_cost_source,
            allocation_rationale=self.allocation_rationale,
            billing_period_start=self.billing_period_start.isoformat(),
            billing_period_end=self.billing_period_end.isoformat(),
            closure=self.closure,
            rounding=self.rounding,
            charge_scope=self.charge_scope,
            zero_cost_evidence=self.zero_cost_evidence,
        )


@dataclass(frozen=True)
class Output:
    inbox: str = "results/inbox"


@dataclass(frozen=True)
class Experiment:
    schema_version: str
    name: str
    challenge: str
    client: str
    provider: str
    model: str
    track: str
    repetitions: int = 1
    client_options: ClientOptions = field(default_factory=ClientOptions)
    budget: Budget = field(default_factory=Budget)
    evaluation: Evaluation = field(default_factory=Evaluation)
    cost: Cost | None = None
    output: Output = field(default_factory=Output)


_TOP = {"schema_version", "name", "challenge", "client", "provider", "model", "track", "repetitions", "client_options", "budget", "evaluation", "cost", "output"}
_CLIENT = {"reasoning_effort", "loop", "executable"}
_BUDGET = {"max_wall_seconds", "max_attempts"}
_EVAL = {"scenario_pack"}
_COST = {"policy", "pool_id", "pool_scope", "currency", "service_plan", "billing_period_cost_usd", "benchmark_allocation_fraction", "pool_cost_usd", "pool_cost_source", "allocation_rationale", "billing_period_start", "billing_period_end", "closure", "rounding", "charge_scope", "zero_cost_evidence"}
_OUTPUT = {"inbox"}
_CLOUD_COST = _COST - {"rounding", "charge_scope", "zero_cost_evidence"}


def _table(raw: Mapping[str, Any], key: str, allowed: set[str]) -> dict[str, Any]:
    value = raw.get(key, {})
    if not isinstance(value, Mapping):
        raise ExperimentError(f"{key} must be a TOML table")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ExperimentError(f"unknown {key} field(s): {', '.join(unknown)}")
    return dict(value)


def _str(raw: Mapping[str, Any], key: str, *, default: str | None = None) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ExperimentError(f"{key} must be a non-empty string")
    return value


def _positive_int(raw: Mapping[str, Any], key: str, default: int) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ExperimentError(f"{key} must be a positive integer")
    return value


def _cost(raw: Mapping[str, Any]) -> Cost:
    missing = sorted(_CLOUD_COST - set(raw))
    if missing:
        raise ExperimentError("cloud experiment cost is missing required field(s): " + ", ".join(missing))
    strings = ["policy", "pool_id", "pool_scope", "currency", "service_plan", "billing_period_cost_usd", "benchmark_allocation_fraction", "pool_cost_usd", "pool_cost_source", "allocation_rationale", "closure"]
    values: dict[str, Any] = {}
    for key in strings:
        values[key] = _str(raw, key)
    try:
        start_value = raw["billing_period_start"]
        end_value = raw["billing_period_end"]
        start = start_value if isinstance(start_value, date) else date.fromisoformat(_str(raw, "billing_period_start"))
        end = end_value if isinstance(end_value, date) else date.fromisoformat(_str(raw, "billing_period_end"))
    except ValueError as exc:
        raise ExperimentError("cost.billing_period_start/end must be ISO dates") from exc
    if end < start:
        raise ExperimentError("cost.billing_period_end must not precede billing_period_start")
    values["rounding"] = _str(raw, "rounding", default="USD-0.01-half-up")
    values["charge_scope"] = _str(raw, "charge_scope", default="model_invocation")
    zero = raw.get("zero_cost_evidence")
    if zero is not None and (not isinstance(zero, str) or not zero.strip()):
        raise ExperimentError("cost.zero_cost_evidence must be a non-empty string")
    values["zero_cost_evidence"] = zero
    values["billing_period_start"] = start.isoformat()
    values["billing_period_end"] = end.isoformat()
    try:
        declaration = FlatSubscriptionPoolDeclaration(**values)
    except CostValidationError as exc:
        raise ExperimentError(f"invalid cost declaration: {exc}") from exc
    values.update(
        billing_period_cost_usd=format(declaration.billing_period_cost_usd, "f"),
        benchmark_allocation_fraction=format(declaration.benchmark_allocation_fraction, "f"),
        pool_cost_usd=format(declaration.pool_cost_usd, "f"),
        billing_period_start=start,
        billing_period_end=end,
    )
    return Cost(**values)


def parse_experiment(data: Mapping[str, Any]) -> Experiment:
    unknown = sorted(set(data) - _TOP)
    if unknown:
        raise ExperimentError("unknown experiment field(s): " + ", ".join(unknown))
    schema = _str(data, "schema_version")
    if schema != "experiment/v1":
        raise ExperimentError(f"unsupported schema_version: {schema!r}; expected 'experiment/v1'")
    client_options = _table(data, "client_options", _CLIENT)
    budget = _table(data, "budget", _BUDGET)
    evaluation = _table(data, "evaluation", _EVAL)
    output = _table(data, "output", _OUTPUT)
    client = _str(data, "client")
    provider = _str(data, "provider")
    track = _str(data, "track")
    if track not in {"cloud-subscription", "cloud-metered", "local"}:
        raise ExperimentError(f"unsupported track: {track!r}")
    cost_raw = _table(data, "cost", _COST) if "cost" in data else None
    cost = _cost(cost_raw) if cost_raw is not None else None
    if track.startswith("cloud-") and cost is None:
        raise ExperimentError("cloud experiments require a [cost] table with flat-subscription cost evidence")
    if track == "cloud-metered":
        raise ExperimentError("cloud-metered experiments require a metered cost policy; flat subscription cost is incompatible")
    if track == "local" and cost is not None:
        raise ExperimentError("local experiments must not declare cloud subscription cost")
    loop = _str(client_options, "loop", default="controlled")
    effort = _str(client_options, "reasoning_effort", default="medium")
    executable_value = client_options.get("executable")
    executable = (
        None
        if executable_value is None
        else _str(client_options, "executable")
    )
    if loop not in {"controlled", "native"}:
        raise ExperimentError(f"unsupported client_options.loop: {loop!r}")
    if effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
        raise ExperimentError(f"unsupported client_options.reasoning_effort: {effort!r}")
    repetitions = _positive_int(data, "repetitions", 1)
    max_wall = _positive_int(budget, "max_wall_seconds", 1200)
    max_attempts = _positive_int(budget, "max_attempts", 2)
    if max_attempts > 2:
        raise ExperimentError("budget.max_attempts cannot exceed one repair attempt (maximum 2)")
    return Experiment(
        schema,
        _str(data, "name"),
        _str(data, "challenge"),
        client,
        provider,
        _str(data, "model"),
        track,
        repetitions,
        ClientOptions(effort, loop, executable),
        Budget(max_wall, max_attempts),
        Evaluation(
            _str(
                evaluation,
                "scenario_pack",
                default="traffic-intersection-p0a",
            )
        ),
        cost,
        Output(_str(output, "inbox", default="results/inbox")),
    )


def load_experiment(path: str | os.PathLike[str]) -> Experiment:
    source = Path(path)
    try:
        with source.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ExperimentError(f"invalid TOML in {source}: {exc}") from exc
    return parse_experiment(data)


def _q(value: str) -> str:
    # JSON basic-string escaping is also valid TOML and covers every control
    # character, unlike a hand-written quote/backslash-only escape.
    return json.dumps(value, ensure_ascii=False)


def render_experiment(experiment: Experiment) -> str:
    """Render canonical TOML with stable section and key ordering."""
    e = experiment
    lines = [
        f"schema_version = {_q(e.schema_version)}",
        f"name = {_q(e.name)}",
        f"challenge = {_q(e.challenge)}",
        f"client = {_q(e.client)}",
        f"provider = {_q(e.provider)}",
        f"model = {_q(e.model)}",
        f"track = {_q(e.track)}",
        f"repetitions = {e.repetitions}",
        "",
        "[client_options]",
        f"reasoning_effort = {_q(e.client_options.reasoning_effort)}",
        f"loop = {_q(e.client_options.loop)}",
    ]
    if e.client_options.executable is not None:
        lines.append(f"executable = {_q(e.client_options.executable)}")
    lines += [
        "",
        "[budget]",
        f"max_wall_seconds = {e.budget.max_wall_seconds}",
        f"max_attempts = {e.budget.max_attempts}",
        "",
        "[evaluation]",
        f"scenario_pack = {_q(e.evaluation.scenario_pack)}",
    ]
    if e.cost is not None:
        c = e.cost
        entries = [
            ("policy", c.policy),
            ("pool_id", c.pool_id),
            ("pool_scope", c.pool_scope),
            ("currency", c.currency),
            ("service_plan", c.service_plan),
            ("billing_period_cost_usd", c.billing_period_cost_usd),
            ("benchmark_allocation_fraction", c.benchmark_allocation_fraction),
            ("pool_cost_usd", c.pool_cost_usd),
            ("pool_cost_source", c.pool_cost_source),
            ("allocation_rationale", c.allocation_rationale),
            ("billing_period_start", c.billing_period_start.isoformat()),
            ("billing_period_end", c.billing_period_end.isoformat()),
            ("closure", c.closure),
            ("rounding", c.rounding),
            ("charge_scope", c.charge_scope),
        ]
        if c.zero_cost_evidence is not None:
            entries.append(("zero_cost_evidence", c.zero_cost_evidence))
        lines += ["", "[cost]"] + [f"{key} = {_q(str(value))}" for key, value in entries]
    lines += ["", "[output]", f"inbox = {_q(e.output.inbox)}", ""]
    return "\n".join(lines)


def save_experiment(experiment: Experiment, path: str | os.PathLike[str]) -> Path:
    """Atomically create a TOML file, refusing to overwrite an existing file."""
    validated = parse_experiment(experiment_to_dict(experiment))
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"experiment already exists: {destination}")
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(render_experiment(validated))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise FileExistsError(f"experiment already exists: {destination}") from exc
        os.unlink(temporary)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


def experiment_to_dict(e: Experiment) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": e.schema_version,
        "name": e.name,
        "challenge": e.challenge,
        "client": e.client,
        "provider": e.provider,
        "model": e.model,
        "track": e.track,
        "repetitions": e.repetitions,
        "client_options": {
            "reasoning_effort": e.client_options.reasoning_effort,
            "loop": e.client_options.loop,
        },
        "budget": {
            "max_wall_seconds": e.budget.max_wall_seconds,
            "max_attempts": e.budget.max_attempts,
        },
        "evaluation": {"scenario_pack": e.evaluation.scenario_pack},
        "output": {"inbox": e.output.inbox},
    }
    if e.client_options.executable is not None:
        result["client_options"]["executable"] = e.client_options.executable
    if e.cost:
        result["cost"] = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in vars(e.cost).items()}
    return result
