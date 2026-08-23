"""Public ``traffic/v1`` value objects and the Busy Intersection fixture.

The browser side of Ralph Bench is deliberately represented by plain JSON at
this boundary.  These objects are small, immutable, and intentionally do not
contain a renderer or a simulation loop.  A browser adapter can translate the
objects to JavaScript while model-free tests can exercise the evaluator with
the same payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Sequence


TRAFFIC_PROTOCOL = "traffic/v1"
SCENARIO_SCHEMA = "scenario/v1"
SNAPSHOT_SCHEMA = "snapshot/v1"
EVENT_SCHEMA = "event/v1"
# Public scenario-pack seeds.  Repetitions cycle only after every declared
# independent seed has been used, and the selected value is recorded in the
# resulting scenario/evidence bundle.
BALANCED_SEEDS = (17, 29, 43)


class TrafficSchemaError(ValueError):
    """Raised when a traffic boundary object is malformed."""


def _value(data: Mapping[str, Any], name: str, default: Any = None) -> Any:
    """Read either the Python or browser-style spelling of a field."""

    if name in data:
        return data[name]
    camel = name.split("_")
    camel_name = camel[0] + "".join(part.title() for part in camel[1:])
    return data.get(camel_name, default)


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrafficSchemaError(f"{field_name} must be a non-empty string")
    return value.strip()


def _number(value: Any, field_name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TrafficSchemaError(f"{field_name} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise TrafficSchemaError(f"{field_name} must be finite")
    if minimum is not None and value < minimum:
        raise TrafficSchemaError(f"{field_name} must be at least {minimum}")
    return value


def _integer(value: Any, field_name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TrafficSchemaError(f"{field_name} must be an integer")
    if minimum is not None and value < minimum:
        raise TrafficSchemaError(f"{field_name} must be at least {minimum}")
    return value


def _tuple_text(values: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise TrafficSchemaError(f"{field_name} must be an array")
    result = tuple(_text(item, f"{field_name}[]") for item in values)
    if len(set(result)) != len(result):
        raise TrafficSchemaError(f"{field_name} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class LaneSegment:
    id: str
    approach: str
    direction: str
    length_m: float = 120.0
    speed_limit_mps: float = 13.4
    storage_m: float = 90.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "lane_segment.id"))
        object.__setattr__(self, "approach", _text(self.approach, "lane_segment.approach"))
        object.__setattr__(self, "direction", _text(self.direction, "lane_segment.direction"))
        object.__setattr__(self, "length_m", _number(self.length_m, "lane_segment.length_m", minimum=1))
        object.__setattr__(self, "speed_limit_mps", _number(self.speed_limit_mps, "lane_segment.speed_limit_mps", minimum=0.1))
        object.__setattr__(self, "storage_m", _number(self.storage_m, "lane_segment.storage_m", minimum=1))
        if self.storage_m > self.length_m:
            raise TrafficSchemaError("lane_segment.storage_m cannot exceed length_m")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "approach": self.approach,
            "direction": self.direction,
            "length_m": self.length_m,
            "speed_limit_mps": self.speed_limit_mps,
            "storage_m": self.storage_m,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "LaneSegment":
        return cls(
            _value(raw, "id"),
            _value(raw, "approach"),
            _value(raw, "direction"),
            _value(raw, "length_m", 120.0),
            _value(raw, "speed_limit_mps", 13.4),
            _value(raw, "storage_m", 90.0),
        )


@dataclass(frozen=True, slots=True)
class Movement:
    id: str
    origin: str
    destination: str
    turn: str
    lane_segments: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "movement.id"))
        object.__setattr__(self, "origin", _text(self.origin, "movement.origin"))
        object.__setattr__(self, "destination", _text(self.destination, "movement.destination"))
        object.__setattr__(self, "turn", _text(self.turn, "movement.turn"))
        if self.turn not in {"left", "straight", "right"}:
            raise TrafficSchemaError("movement.turn must be left, straight, or right")
        object.__setattr__(self, "lane_segments", _tuple_text(self.lane_segments, "movement.lane_segments"))
        if self.origin == self.destination:
            raise TrafficSchemaError("movement origin and destination must differ")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "origin": self.origin,
            "destination": self.destination,
            "turn": self.turn,
            "lane_segments": list(self.lane_segments),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Movement":
        return cls(
            _value(raw, "id"),
            _value(raw, "origin"),
            _value(raw, "destination"),
            _value(raw, "turn"),
            _value(raw, "lane_segments", ()),
        )


@dataclass(frozen=True, slots=True)
class Crossing:
    id: str
    approach: str
    length_m: float = 18.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "crossing.id"))
        object.__setattr__(self, "approach", _text(self.approach, "crossing.approach"))
        object.__setattr__(self, "length_m", _number(self.length_m, "crossing.length_m", minimum=1))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "approach": self.approach, "length_m": self.length_m}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Crossing":
        return cls(_value(raw, "id"), _value(raw, "approach"), _value(raw, "length_m", 18.0))


@dataclass(frozen=True, slots=True)
class NetworkDescription:
    nodes: tuple[str, ...]
    lane_segments: tuple[LaneSegment, ...]
    movements: tuple[Movement, ...]
    crossings: tuple[Crossing, ...]
    vehicle_length_m: float = 4.8
    max_acceleration_mps2: float = 2.5
    comfortable_braking_mps2: float = 4.0
    minimum_headway_m: float = 7.0
    grade_separation: bool = False
    api_version: str = TRAFFIC_PROTOCOL

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", _tuple_text(self.nodes, "network.nodes"))
        object.__setattr__(self, "vehicle_length_m", _number(self.vehicle_length_m, "network.vehicle_length_m", minimum=0.1))
        object.__setattr__(self, "max_acceleration_mps2", _number(self.max_acceleration_mps2, "network.max_acceleration_mps2", minimum=0.1))
        object.__setattr__(self, "comfortable_braking_mps2", _number(self.comfortable_braking_mps2, "network.comfortable_braking_mps2", minimum=0.1))
        object.__setattr__(self, "minimum_headway_m", _number(self.minimum_headway_m, "network.minimum_headway_m", minimum=0.1))
        if self.api_version != TRAFFIC_PROTOCOL:
            raise TrafficSchemaError(f"unsupported traffic protocol: {self.api_version!r}")
        lane_ids = {lane.id for lane in self.lane_segments}
        movement_ids = {movement.id for movement in self.movements}
        if len(lane_ids) != len(self.lane_segments) or len(movement_ids) != len(self.movements):
            raise TrafficSchemaError("network IDs must be unique")
        node_set = set(self.nodes)
        if any(m.origin not in node_set or m.destination not in node_set for m in self.movements):
            raise TrafficSchemaError("movement endpoint is not declared in network.nodes")
        if any(lane_id not in lane_ids for movement in self.movements for lane_id in movement.lane_segments):
            raise TrafficSchemaError("movement references an unknown lane segment")
        if len({crossing.id for crossing in self.crossings}) != len(self.crossings):
            raise TrafficSchemaError("crossing IDs must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_version": self.api_version,
            "nodes": list(self.nodes),
            "lane_segments": [item.to_dict() for item in self.lane_segments],
            "movements": [item.to_dict() for item in self.movements],
            "crossings": [item.to_dict() for item in self.crossings],
            "constraints": {
                "vehicle_length_m": self.vehicle_length_m,
                "max_acceleration_mps2": self.max_acceleration_mps2,
                "comfortable_braking_mps2": self.comfortable_braking_mps2,
                "minimum_headway_m": self.minimum_headway_m,
                "grade_separation": self.grade_separation,
            },
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "NetworkDescription":
        constraints = _value(raw, "constraints", {})
        if not isinstance(constraints, Mapping):
            raise TrafficSchemaError("network.constraints must be an object")
        return cls(
            _value(raw, "nodes", ()),
            tuple(LaneSegment.from_dict(item) for item in _value(raw, "lane_segments", ())),
            tuple(Movement.from_dict(item) for item in _value(raw, "movements", ())),
            tuple(Crossing.from_dict(item) for item in _value(raw, "crossings", ())),
            _value(constraints, "vehicle_length_m", 4.8),
            _value(constraints, "max_acceleration_mps2", 2.5),
            _value(constraints, "comfortable_braking_mps2", 4.0),
            _value(constraints, "minimum_headway_m", 7.0),
            _value(constraints, "grade_separation", False),
            _value(raw, "api_version", TRAFFIC_PROTOCOL),
        )


@dataclass(frozen=True, slots=True)
class DemandStage:
    id: str
    start_ms: int
    end_ms: int
    offered_trips_per_hour: int
    pedestrian_requests_per_hour: int = 0
    qualifying: bool = True
    cooldown: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "stage.id"))
        object.__setattr__(self, "start_ms", _integer(self.start_ms, "stage.start_ms", minimum=0))
        object.__setattr__(self, "end_ms", _integer(self.end_ms, "stage.end_ms", minimum=1))
        object.__setattr__(self, "offered_trips_per_hour", _integer(self.offered_trips_per_hour, "stage.offered_trips_per_hour", minimum=0))
        object.__setattr__(self, "pedestrian_requests_per_hour", _integer(self.pedestrian_requests_per_hour, "stage.pedestrian_requests_per_hour", minimum=0))
        if self.end_ms <= self.start_ms:
            raise TrafficSchemaError("stage.end_ms must be greater than start_ms")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "offered_trips_per_hour": self.offered_trips_per_hour,
            "pedestrian_requests_per_hour": self.pedestrian_requests_per_hour,
            "qualifying": self.qualifying,
            "cooldown": self.cooldown,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "DemandStage":
        return cls(
            _value(raw, "id"),
            _value(raw, "start_ms", 0),
            _value(raw, "end_ms", 1),
            _value(raw, "offered_trips_per_hour", 0),
            _value(raw, "pedestrian_requests_per_hour", 0),
            _value(raw, "qualifying", True),
            _value(raw, "cooldown", False),
        )


@dataclass(frozen=True, slots=True)
class VehicleTrip:
    trip_id: str
    origin: str
    destination: str
    movement_id: str
    departure_ms: int
    vehicle_type: str = "passenger"

    def __post_init__(self) -> None:
        object.__setattr__(self, "trip_id", _text(self.trip_id, "trip.trip_id"))
        object.__setattr__(self, "origin", _text(self.origin, "trip.origin"))
        object.__setattr__(self, "destination", _text(self.destination, "trip.destination"))
        object.__setattr__(self, "movement_id", _text(self.movement_id, "trip.movement_id"))
        object.__setattr__(self, "departure_ms", _integer(self.departure_ms, "trip.departure_ms", minimum=0))
        object.__setattr__(self, "vehicle_type", _text(self.vehicle_type, "trip.vehicle_type"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "trip_id": self.trip_id,
            "origin": self.origin,
            "destination": self.destination,
            "movement_id": self.movement_id,
            "departure_ms": self.departure_ms,
            "vehicle_type": self.vehicle_type,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "VehicleTrip":
        return cls(
            _value(raw, "trip_id"),
            _value(raw, "origin"),
            _value(raw, "destination"),
            _value(raw, "movement_id"),
            _value(raw, "departure_ms", 0),
            _value(raw, "vehicle_type", "passenger"),
        )


@dataclass(frozen=True, slots=True)
class PedestrianRequest:
    request_id: str
    crossing_id: str
    request_ms: int
    duration_ms: int = 5000

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _text(self.request_id, "pedestrian.request_id"))
        object.__setattr__(self, "crossing_id", _text(self.crossing_id, "pedestrian.crossing_id"))
        object.__setattr__(self, "request_ms", _integer(self.request_ms, "pedestrian.request_ms", minimum=0))
        object.__setattr__(self, "duration_ms", _integer(self.duration_ms, "pedestrian.duration_ms", minimum=1))

    def to_dict(self) -> dict[str, Any]:
        return {"request_id": self.request_id, "crossing_id": self.crossing_id, "request_ms": self.request_ms, "duration_ms": self.duration_ms}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PedestrianRequest":
        return cls(_value(raw, "request_id"), _value(raw, "crossing_id"), _value(raw, "request_ms", 0), _value(raw, "duration_ms", 5000))


@dataclass(frozen=True, slots=True)
class Scenario:
    scenario_id: str
    profile: str
    seed: int
    horizon_ms: int
    stages: tuple[DemandStage, ...]
    trips: tuple[VehicleTrip, ...]
    pedestrians: tuple[PedestrianRequest, ...] = ()
    schema_version: str = SCENARIO_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", _text(self.scenario_id, "scenario.scenario_id"))
        object.__setattr__(self, "profile", _text(self.profile, "scenario.profile"))
        object.__setattr__(self, "seed", _integer(self.seed, "scenario.seed"))
        object.__setattr__(self, "horizon_ms", _integer(self.horizon_ms, "scenario.horizon_ms", minimum=1))
        if self.schema_version != SCENARIO_SCHEMA:
            raise TrafficSchemaError(f"unsupported scenario schema: {self.schema_version!r}")
        if not self.stages:
            raise TrafficSchemaError("scenario must contain at least one stage")
        if self.stages[0].start_ms != 0 or self.stages[-1].end_ms > self.horizon_ms:
            raise TrafficSchemaError("scenario stages must fit within the horizon")
        previous_end = 0
        for stage in self.stages:
            if stage.start_ms != previous_end:
                raise TrafficSchemaError("scenario stages must be contiguous")
            previous_end = stage.end_ms
        trip_ids = [trip.trip_id for trip in self.trips]
        if len(set(trip_ids)) != len(trip_ids):
            raise TrafficSchemaError("scenario trip IDs must be unique")
        pedestrian_ids = [item.request_id for item in self.pedestrians]
        if len(set(pedestrian_ids)) != len(pedestrian_ids):
            raise TrafficSchemaError("scenario pedestrian request IDs must be unique")
        if any(trip.departure_ms >= self.horizon_ms for trip in self.trips):
            raise TrafficSchemaError("trip departure must be within the scenario horizon")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "profile": self.profile,
            "seed": self.seed,
            "horizon_ms": self.horizon_ms,
            "stages": [stage.to_dict() for stage in self.stages],
            "trips": [trip.to_dict() for trip in self.trips],
            "pedestrians": [item.to_dict() for item in self.pedestrians],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Scenario":
        return cls(
            _value(raw, "scenario_id"),
            _value(raw, "profile"),
            _value(raw, "seed"),
            _value(raw, "horizon_ms"),
            tuple(DemandStage.from_dict(item) for item in _value(raw, "stages", ())),
            tuple(VehicleTrip.from_dict(item) for item in _value(raw, "trips", ())),
            tuple(PedestrianRequest.from_dict(item) for item in _value(raw, "pedestrians", ())),
            _value(raw, "schema_version", SCENARIO_SCHEMA),
        )


@dataclass(frozen=True, slots=True)
class VehicleObservation:
    trip_id: str
    movement_id: str
    lane_segment_id: str
    position_m: float
    speed_mps: float
    length_m: float = 4.8
    status: str = "active"
    entered_on_red: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "trip_id", _text(self.trip_id, "vehicle.trip_id"))
        object.__setattr__(self, "movement_id", _text(self.movement_id, "vehicle.movement_id"))
        object.__setattr__(self, "lane_segment_id", _text(self.lane_segment_id, "vehicle.lane_segment_id"))
        object.__setattr__(self, "position_m", _number(self.position_m, "vehicle.position_m", minimum=0))
        object.__setattr__(self, "speed_mps", _number(self.speed_mps, "vehicle.speed_mps", minimum=0))
        object.__setattr__(self, "length_m", _number(self.length_m, "vehicle.length_m", minimum=0.1))
        object.__setattr__(self, "status", _text(self.status, "vehicle.status"))

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "VehicleObservation":
        return cls(_value(raw, "trip_id"), _value(raw, "movement_id"), _value(raw, "lane_segment_id"), _value(raw, "position_m", 0), _value(raw, "speed_mps", 0), _value(raw, "length_m", 4.8), _value(raw, "status", "active"), _value(raw, "entered_on_red", False))

    def to_dict(self) -> dict[str, Any]:
        return {"trip_id": self.trip_id, "movement_id": self.movement_id, "lane_segment_id": self.lane_segment_id, "position_m": self.position_m, "speed_mps": self.speed_mps, "length_m": self.length_m, "status": self.status, "entered_on_red": self.entered_on_red}


@dataclass(frozen=True, slots=True)
class PedestrianObservation:
    request_id: str
    crossing_id: str
    position_m: float
    status: str = "waiting"

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PedestrianObservation":
        return cls(_value(raw, "request_id"), _value(raw, "crossing_id"), _value(raw, "position_m", 0), _value(raw, "status", "waiting"))

    def to_dict(self) -> dict[str, Any]:
        return {"request_id": self.request_id, "crossing_id": self.crossing_id, "position_m": self.position_m, "status": self.status}


@dataclass(frozen=True, slots=True)
class SignalObservation:
    movement_id: str
    state: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "movement_id", _text(self.movement_id, "signal.movement_id"))
        object.__setattr__(self, "state", _text(self.state, "signal.state").lower())
        if self.state not in {"red", "yellow", "green", "walk", "dont_walk"}:
            raise TrafficSchemaError("signal.state is not recognized")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "SignalObservation":
        return cls(_value(raw, "movement_id"), _value(raw, "state"))

    def to_dict(self) -> dict[str, Any]:
        return {"movement_id": self.movement_id, "state": self.state}


@dataclass(frozen=True, slots=True)
class QueueObservation:
    approach: str
    vehicle_count: int
    length_m: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "approach", _text(self.approach, "queue.approach"))
        object.__setattr__(self, "vehicle_count", _integer(self.vehicle_count, "queue.vehicle_count", minimum=0))
        object.__setattr__(self, "length_m", _number(self.length_m, "queue.length_m", minimum=0))

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "QueueObservation":
        return cls(_value(raw, "approach"), _value(raw, "vehicle_count", 0), _value(raw, "length_m", 0))

    def to_dict(self) -> dict[str, Any]:
        return {"approach": self.approach, "vehicle_count": self.vehicle_count, "length_m": self.length_m}


@dataclass(frozen=True, slots=True)
class TripObservation:
    trip_id: str
    status: str
    origin: str | None = None
    destination: str | None = None
    movement_id: str | None = None
    admitted_ms: int | None = None
    completed_ms: int | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "trip_id", _text(self.trip_id, "trip_observation.trip_id"))
        object.__setattr__(self, "status", _text(self.status, "trip_observation.status").lower())
        if self.status not in {"requested", "admitted", "active", "completed", "explicitly_rejected", "lost"}:
            raise TrafficSchemaError("trip_observation.status is not recognized")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "TripObservation":
        return cls(_value(raw, "trip_id"), _value(raw, "status"), _value(raw, "origin"), _value(raw, "destination"), _value(raw, "movement_id"), _value(raw, "admitted_ms"), _value(raw, "completed_ms"), _value(raw, "reason"))

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in {"trip_id": self.trip_id, "status": self.status, "origin": self.origin, "destination": self.destination, "movement_id": self.movement_id, "admitted_ms": self.admitted_ms, "completed_ms": self.completed_ms, "reason": self.reason}.items() if value is not None}


@dataclass(frozen=True, slots=True)
class TrafficSnapshot:
    time_ms: int
    vehicles: tuple[VehicleObservation, ...] = ()
    pedestrians: tuple[PedestrianObservation, ...] = ()
    signals: tuple[SignalObservation, ...] = ()
    queues: tuple[QueueObservation, ...] = ()
    trips: tuple[TripObservation, ...] = ()
    runtime_errors: tuple[str, ...] = ()
    schema_version: str = SNAPSHOT_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "time_ms", _integer(self.time_ms, "snapshot.time_ms", minimum=0))
        if self.schema_version != SNAPSHOT_SCHEMA:
            raise TrafficSchemaError(f"unsupported snapshot schema: {self.schema_version!r}")
        object.__setattr__(self, "runtime_errors", _tuple_text(self.runtime_errors, "snapshot.runtime_errors"))

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "TrafficSnapshot":
        return cls(
            _value(raw, "time_ms", 0),
            tuple(VehicleObservation.from_dict(item) for item in _value(raw, "vehicles", ())),
            tuple(PedestrianObservation.from_dict(item) for item in _value(raw, "pedestrians", ())),
            tuple(SignalObservation.from_dict(item) for item in _value(raw, "signals", ())),
            tuple(QueueObservation.from_dict(item) for item in _value(raw, "queues", ())),
            tuple(TripObservation.from_dict(item) for item in _value(raw, "trips", ())),
            tuple(_text(item, "snapshot.runtime_errors[]") for item in _value(raw, "runtime_errors", ())),
            _value(raw, "schema_version", SNAPSHOT_SCHEMA),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "time_ms": self.time_ms,
            "vehicles": [item.to_dict() for item in self.vehicles],
            "pedestrians": [item.to_dict() for item in self.pedestrians],
            "signals": [item.to_dict() for item in self.signals],
            "queues": [item.to_dict() for item in self.queues],
            "trips": [item.to_dict() for item in self.trips],
            "runtime_errors": list(self.runtime_errors),
        }


@dataclass(frozen=True, slots=True)
class TrafficEvent:
    sequence: int
    time_ms: int
    event_type: str
    entity_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = EVENT_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _integer(self.sequence, "event.sequence", minimum=0))
        object.__setattr__(self, "time_ms", _integer(self.time_ms, "event.time_ms", minimum=0))
        object.__setattr__(self, "event_type", _text(self.event_type, "event.event_type"))
        object.__setattr__(self, "entity_id", _text(self.entity_id, "event.entity_id"))
        if not isinstance(self.payload, Mapping):
            raise TrafficSchemaError("event.payload must be an object")
        if self.schema_version != EVENT_SCHEMA:
            raise TrafficSchemaError(f"unsupported event schema: {self.schema_version!r}")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "TrafficEvent":
        return cls(_value(raw, "sequence", 0), _value(raw, "time_ms", 0), _value(raw, "event_type", _value(raw, "type")), _value(raw, "entity_id", "network"), _value(raw, "payload", {}), _value(raw, "schema_version", EVENT_SCHEMA))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "sequence": self.sequence, "time_ms": self.time_ms, "event_type": self.event_type, "entity_id": self.entity_id, "payload": dict(self.payload)}


def busy_intersection_network() -> NetworkDescription:
    """Return the technology-neutral four-way P0-A infrastructure envelope."""

    approaches = ("north", "east", "south", "west")
    lanes = tuple(
        LaneSegment(f"{approach}-in", approach, "inbound")
        for approach in approaches
    ) + tuple(
        LaneSegment(f"{approach}-out", approach, "outbound")
        for approach in approaches
    )
    movements: list[Movement] = []
    for origin_index, origin in enumerate(approaches):
        for destination_index, destination in enumerate(approaches):
            if origin == destination:
                continue
            delta = (destination_index - origin_index) % len(approaches)
            turn = "straight" if delta == 2 else ("right" if delta == 1 else "left")
            movements.append(
                Movement(
                    f"{origin}-{turn}-{destination}",
                    origin,
                    destination,
                    turn,
                    (f"{origin}-in", f"{destination}-out"),
                )
            )
    crossings = tuple(Crossing(f"{approach}-crossing", approach) for approach in approaches)
    return NetworkDescription(approaches, lanes, tuple(movements), crossings)


def balanced_stages() -> tuple[DemandStage, ...]:
    """Deterministic P0-A held stages, including a recovery interval."""

    return (
        DemandStage("warmup", 0, 60_000, 240, 60),
        DemandStage("balanced-1", 60_000, 180_000, 600, 120),
        DemandStage("balanced-2", 180_000, 300_000, 900, 180),
        DemandStage("balanced-3", 300_000, 420_000, 1_200, 240),
        DemandStage("balanced-4", 420_000, 540_000, 1_500, 300),
        DemandStage("cooldown", 540_000, 660_000, 0, 0, False, True),
    )


def _next_random(state: int) -> tuple[int, int]:
    state = (state * 1_664_525 + 1_013_904_223) & 0xFFFFFFFF
    return state, state


def build_balanced_scenario(seed: int = 17) -> Scenario:
    """Build a reproducible evaluator-owned demand schedule.

    Demand is spread evenly over each held stage; the seeded movement choice
    changes the mix without changing the offered rate or stage boundaries.
    """

    network = busy_intersection_network()
    stages = balanced_stages()
    movements = network.movements
    trips: list[VehicleTrip] = []
    pedestrians: list[PedestrianRequest] = []
    random_state = seed & 0xFFFFFFFF
    trip_number = 0
    pedestrian_number = 0
    for stage in stages:
        count = round(stage.offered_trips_per_hour * stage.duration_ms / 3_600_000)
        interval = stage.duration_ms / count if count else stage.duration_ms
        for offset in range(count):
            random_state, choice = _next_random(random_state)
            movement = movements[choice % len(movements)]
            departure = stage.start_ms + min(stage.duration_ms - 1, round(offset * interval))
            trip_number += 1
            trips.append(VehicleTrip(f"trip-{trip_number:04d}", movement.origin, movement.destination, movement.id, departure))
        pedestrian_count = round(stage.pedestrian_requests_per_hour * stage.duration_ms / 3_600_000)
        ped_interval = stage.duration_ms / pedestrian_count if pedestrian_count else stage.duration_ms
        for offset in range(pedestrian_count):
            pedestrian_number += 1
            crossing = network.crossings[(pedestrian_number + seed) % len(network.crossings)]
            request_ms = stage.start_ms + min(stage.duration_ms - 1, round(offset * ped_interval))
            pedestrians.append(PedestrianRequest(f"ped-{pedestrian_number:04d}", crossing.id, request_ms))
    return Scenario("busy-intersection-balanced", "balanced", seed, stages[-1].end_ms, stages, tuple(trips), tuple(pedestrians))


def balanced_seed_for_repetition(repetition: int) -> int:
    """Map one-based run repetitions deterministically to public seeds."""

    if not isinstance(repetition, int) or isinstance(repetition, bool) or repetition < 1:
        raise ValueError("repetition must be a positive integer")
    return BALANCED_SEEDS[(repetition - 1) % len(BALANCED_SEEDS)]


__all__ = [
    "TRAFFIC_PROTOCOL", "SCENARIO_SCHEMA", "SNAPSHOT_SCHEMA", "EVENT_SCHEMA", "BALANCED_SEEDS",
    "TrafficSchemaError", "LaneSegment", "Movement", "Crossing", "NetworkDescription",
    "DemandStage", "VehicleTrip", "PedestrianRequest", "Scenario", "VehicleObservation",
    "PedestrianObservation", "SignalObservation", "QueueObservation", "TripObservation",
    "TrafficSnapshot", "TrafficEvent", "busy_intersection_network", "balanced_stages",
    "build_balanced_scenario", "balanced_seed_for_repetition",
]
