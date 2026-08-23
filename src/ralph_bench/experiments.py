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
from pathlib import Path
from typing import Any, Mapping

from .challenges import ChallengeProfileError, scenario_pack_for


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
    output: Output = field(default_factory=Output)


_TOP = {"schema_version", "name", "challenge", "client", "provider", "model", "track", "repetitions", "client_options", "budget", "evaluation", "output"}
_CLIENT = {"reasoning_effort", "loop", "executable"}
_BUDGET = {"max_wall_seconds", "max_attempts"}
_EVAL = {"scenario_pack"}
_OUTPUT = {"inbox"}


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
    if track not in {"cloud-subscription", "local"}:
        raise ExperimentError(f"unsupported track: {track!r}")
    challenge = _str(data, "challenge")
    try:
        expected_scenario_pack = scenario_pack_for(challenge, track)
    except ChallengeProfileError as exc:
        raise ExperimentError(str(exc)) from exc
    selected_scenario_pack = _str(
        evaluation,
        "scenario_pack",
        default=expected_scenario_pack,
    )
    if selected_scenario_pack != expected_scenario_pack:
        raise ExperimentError(
            f"evaluation.scenario_pack {selected_scenario_pack!r} is not "
            f"compatible with challenge {challenge!r} on track {track!r}; "
            f"expected {expected_scenario_pack!r}"
        )
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
    if loop == "native" and max_attempts != 1:
        raise ExperimentError(
            "budget.max_attempts must be 1 when client_options.loop is native; "
            "Ralph repair passes apply only to the controlled loop"
        )
    return Experiment(
        schema,
        _str(data, "name"),
        challenge,
        client,
        provider,
        _str(data, "model"),
        track,
        repetitions,
        ClientOptions(effort, loop, executable),
        Budget(max_wall, max_attempts),
        Evaluation(selected_scenario_pack),
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
    return result
