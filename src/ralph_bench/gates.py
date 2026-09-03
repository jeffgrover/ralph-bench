"""Minimal evaluator-owned demand objects for the ``gates/v1`` protocol.

The candidate sees only car and pedestrian arrivals. Ralph owns arrival IDs,
timing, the completion ledger, and derived monitoring evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping


GATES_PROTOCOL = "gates/v1"
GATE_SCENARIO_SCHEMA = "gate-scenario/v1"
BALANCED_SEEDS = (17, 29, 43)
SIDES = ("north", "east", "south", "west")
PEDESTRIAN_DIRECTIONS = {
    "north": ("east-to-west", "west-to-east"),
    "south": ("east-to-west", "west-to-east"),
    "east": ("north-to-south", "south-to-north"),
    "west": ("north-to-south", "south-to-north"),
}


class GateSchemaError(ValueError):
    """A gates/v1 evaluator-owned value is malformed."""


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GateSchemaError(f"{name} must be a non-empty string")
    return value.strip()


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise GateSchemaError(f"{name} must be an integer of at least {minimum}")
    return value


def _rate(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GateSchemaError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise GateSchemaError(f"{name} must be finite and non-negative")
    return result


@dataclass(frozen=True, slots=True)
class DemandStage:
    id: str
    start_ms: int
    end_ms: int
    offered_cars_per_minute: float
    offered_pedestrians_per_minute: float = 0
    qualifying: bool = True
    cooldown: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "stage.id"))
        object.__setattr__(self, "start_ms", _integer(self.start_ms, "stage.start_ms"))
        object.__setattr__(self, "end_ms", _integer(self.end_ms, "stage.end_ms", minimum=1))
        object.__setattr__(self, "offered_cars_per_minute", _rate(self.offered_cars_per_minute, "stage.offered_cars_per_minute"))
        object.__setattr__(self, "offered_pedestrians_per_minute", _rate(self.offered_pedestrians_per_minute, "stage.offered_pedestrians_per_minute"))
        if self.end_ms <= self.start_ms:
            raise GateSchemaError("stage.end_ms must be greater than start_ms")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "offered_cars_per_minute": self.offered_cars_per_minute,
            "offered_pedestrians_per_minute": self.offered_pedestrians_per_minute,
            "qualifying": self.qualifying,
            "cooldown": self.cooldown,
        }


@dataclass(frozen=True, slots=True)
class CarArrival:
    id: str
    enters_from: str
    exits_to: str
    arrival_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "car.id"))
        object.__setattr__(self, "enters_from", _text(self.enters_from, "car.enters_from").lower())
        object.__setattr__(self, "exits_to", _text(self.exits_to, "car.exits_to").lower())
        object.__setattr__(self, "arrival_ms", _integer(self.arrival_ms, "car.arrival_ms"))
        if self.enters_from not in SIDES or self.exits_to not in SIDES:
            raise GateSchemaError("car gates must be north, east, south, or west")
        if self.enters_from == self.exits_to:
            raise GateSchemaError("gates/v1 does not request U-turns")

    def to_public_dict(self) -> dict[str, str]:
        return {"id": self.id, "entersFrom": self.enters_from, "exitsTo": self.exits_to}

    def to_dict(self) -> dict[str, Any]:
        return {**self.to_public_dict(), "arrival_ms": self.arrival_ms}


@dataclass(frozen=True, slots=True)
class PedestrianArrival:
    id: str
    crossing: str
    direction: str
    arrival_ms: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "pedestrian.id"))
        object.__setattr__(self, "crossing", _text(self.crossing, "pedestrian.crossing").lower())
        object.__setattr__(self, "direction", _text(self.direction, "pedestrian.direction").lower())
        object.__setattr__(self, "arrival_ms", _integer(self.arrival_ms, "pedestrian.arrival_ms"))
        if self.crossing not in SIDES:
            raise GateSchemaError("pedestrian crossing must be north, east, south, or west")
        if self.direction not in PEDESTRIAN_DIRECTIONS[self.crossing]:
            raise GateSchemaError("pedestrian direction does not cross the selected road")

    def to_public_dict(self) -> dict[str, str]:
        return {"id": self.id, "crossing": self.crossing, "direction": self.direction}

    def to_dict(self) -> dict[str, Any]:
        return {**self.to_public_dict(), "arrival_ms": self.arrival_ms}


@dataclass(frozen=True, slots=True)
class GateScenario:
    scenario_id: str
    profile: str
    seed: int
    horizon_ms: int
    stages: tuple[DemandStage, ...]
    cars: tuple[CarArrival, ...]
    pedestrians: tuple[PedestrianArrival, ...]
    schema_version: str = GATE_SCENARIO_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", _text(self.scenario_id, "scenario.scenario_id"))
        object.__setattr__(self, "profile", _text(self.profile, "scenario.profile"))
        object.__setattr__(self, "seed", _integer(self.seed, "scenario.seed"))
        object.__setattr__(self, "horizon_ms", _integer(self.horizon_ms, "scenario.horizon_ms", minimum=1))
        if self.schema_version != GATE_SCENARIO_SCHEMA:
            raise GateSchemaError(f"unsupported gate scenario schema: {self.schema_version!r}")
        if not self.stages or self.stages[0].start_ms != 0 or self.stages[-1].end_ms != self.horizon_ms:
            raise GateSchemaError("scenario stages must cover the complete horizon")
        previous_end = 0
        for stage in self.stages:
            if stage.start_ms != previous_end:
                raise GateSchemaError("scenario stages must be contiguous")
            previous_end = stage.end_ms
        ids = [item.id for item in (*self.cars, *self.pedestrians)]
        if len(ids) != len(set(ids)):
            raise GateSchemaError("arrival IDs must be unique across the scenario")
        if any(item.arrival_ms >= self.horizon_ms for item in (*self.cars, *self.pedestrians)):
            raise GateSchemaError("arrivals must occur within the scenario horizon")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "protocol": GATES_PROTOCOL,
            "scenario_id": self.scenario_id,
            "profile": self.profile,
            "seed": self.seed,
            "horizon_ms": self.horizon_ms,
            "stages": [item.to_dict() for item in self.stages],
            "cars": [item.to_dict() for item in self.cars],
            "pedestrians": [item.to_dict() for item in self.pedestrians],
        }


def balanced_stages() -> tuple[DemandStage, ...]:
    """Wall-clock stages long enough to observe a complete visual signal cycle."""

    return (
        DemandStage("warmup", 0, 20_000, 15, 3),
        DemandStage("load-1", 20_000, 40_000, 30, 6),
        DemandStage("load-2", 40_000, 60_000, 45, 9),
        DemandStage("load-3", 60_000, 80_000, 60, 12),
        DemandStage("load-4", 80_000, 100_000, 90, 18),
        DemandStage("cooldown", 100_000, 130_000, 0, 0, False, True),
    )


def _next_random(state: int) -> tuple[int, int]:
    state = (state * 1_664_525 + 1_013_904_223) & 0xFFFFFFFF
    return state, state


def build_balanced_gate_scenario(seed: int = 17) -> GateScenario:
    stages = balanced_stages()
    cars: list[CarArrival] = []
    pedestrians: list[PedestrianArrival] = []
    state = seed & 0xFFFFFFFF
    for stage in stages:
        car_count = round(stage.offered_cars_per_minute * stage.duration_ms / 60_000)
        for offset in range(car_count):
            state, choice = _next_random(state)
            enters = SIDES[choice % 4]
            destinations = tuple(side for side in SIDES if side != enters)
            exits = destinations[(choice // 4) % len(destinations)]
            arrival = stage.start_ms + round(offset * stage.duration_ms / max(car_count, 1))
            cars.append(CarArrival(f"car-{len(cars) + 1:04d}", enters, exits, arrival))
        pedestrian_count = round(stage.offered_pedestrians_per_minute * stage.duration_ms / 60_000)
        for offset in range(pedestrian_count):
            state, choice = _next_random(state)
            crossing = SIDES[choice % 4]
            directions = PEDESTRIAN_DIRECTIONS[crossing]
            direction = directions[(choice // 4) % 2]
            arrival = stage.start_ms + round(offset * stage.duration_ms / max(pedestrian_count, 1))
            pedestrians.append(PedestrianArrival(f"ped-{len(pedestrians) + 1:04d}", crossing, direction, arrival))
    return GateScenario(
        "busy-intersection-gates-balanced",
        "balanced-gates",
        seed,
        stages[-1].end_ms,
        stages,
        tuple(cars),
        tuple(pedestrians),
    )


def balanced_seed_for_repetition(repetition: int) -> int:
    if isinstance(repetition, bool) or not isinstance(repetition, int) or repetition < 1:
        raise ValueError("repetition must be a positive integer")
    return BALANCED_SEEDS[(repetition - 1) % len(BALANCED_SEEDS)]


def gate_scenario_from_dict(value: Mapping[str, Any]) -> GateScenario:
    """Reconstruct a validated evaluator scenario from its JSON form."""

    if not isinstance(value, Mapping):
        raise GateSchemaError("scenario must be an object")
    stages_raw = value.get("stages")
    cars_raw = value.get("cars")
    pedestrians_raw = value.get("pedestrians")
    if not isinstance(stages_raw, list) or not isinstance(cars_raw, list) or not isinstance(pedestrians_raw, list):
        raise GateSchemaError("scenario stages, cars, and pedestrians must be lists")
    stages = tuple(
        DemandStage(
            item["id"],
            item["start_ms"],
            item["end_ms"],
            item["offered_cars_per_minute"],
            item.get("offered_pedestrians_per_minute", 0),
            item.get("qualifying", True),
            item.get("cooldown", False),
        )
        for item in stages_raw
        if isinstance(item, Mapping)
    )
    cars = tuple(
        CarArrival(
            item["id"],
            item["entersFrom"],
            item["exitsTo"],
            item["arrival_ms"],
        )
        for item in cars_raw
        if isinstance(item, Mapping)
    )
    pedestrians = tuple(
        PedestrianArrival(
            item["id"],
            item["crossing"],
            item["direction"],
            item["arrival_ms"],
        )
        for item in pedestrians_raw
        if isinstance(item, Mapping)
    )
    if len(stages) != len(stages_raw) or len(cars) != len(cars_raw) or len(pedestrians) != len(pedestrians_raw):
        raise GateSchemaError("scenario entries must be objects")
    return GateScenario(
        value["scenario_id"],
        value["profile"],
        value["seed"],
        value["horizon_ms"],
        stages,
        cars,
        pedestrians,
        value.get("schema_version", GATE_SCENARIO_SCHEMA),
    )


__all__ = [
    "BALANCED_SEEDS",
    "GATES_PROTOCOL",
    "GATE_SCENARIO_SCHEMA",
    "PEDESTRIAN_DIRECTIONS",
    "SIDES",
    "CarArrival",
    "DemandStage",
    "GateScenario",
    "GateSchemaError",
    "PedestrianArrival",
    "balanced_seed_for_repetition",
    "balanced_stages",
    "build_balanced_gate_scenario",
    "gate_scenario_from_dict",
]
