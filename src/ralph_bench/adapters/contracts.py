from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol


@dataclass(frozen=True)
class AdapterDescriptor:
    adapter_id: str
    family: str
    label: str
    version: str = "1.0"
    contract_version: str = "adapter/v1"
    option_schema_version: str = "options/v1"
    capabilities: tuple[str, ...] = ()
    detection: str = "manual"
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.family not in {"harness", "provider", "model"}:
            raise ValueError(f"unsupported adapter family: {self.family!r}")
        if not self.adapter_id.startswith(f"{self.family}/"):
            raise ValueError(
                f"adapter ID {self.adapter_id!r} must start with "
                f"{self.family + '/'!r}"
            )
        for name, value in (
            ("adapter_id", self.adapter_id),
            ("label", self.label),
            ("version", self.version),
            ("contract_version", self.contract_version),
            ("option_schema_version", self.option_schema_version),
            ("detection", self.detection),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")
        capabilities = tuple(self.capabilities)
        limitations = tuple(self.limitations)
        if any(not value.strip() for value in capabilities):
            raise ValueError("adapter capabilities must be non-empty strings")
        if len(set(capabilities)) != len(capabilities):
            raise ValueError("adapter capabilities must be unique")
        if any(not value.strip() for value in limitations):
            raise ValueError("adapter limitations must be non-empty strings")
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "limitations", limitations)


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


ProcessRunner = Callable[[tuple[str, ...], float], ProcessResult]


@dataclass(frozen=True)
class ProbeContext:
    # Toolchain refreshes (notably `codex update`) may download a release and
    # legitimately take longer than a lightweight status probe. Keep the
    # bound finite while allowing the normal update path to complete.
    timeout_seconds: float = 30.0
    executable: str | None = None
    process_runner: ProcessRunner | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("probe timeout must be positive")
        if self.executable is not None and not self.executable.strip():
            raise ValueError("probe executable must be non-empty")
        object.__setattr__(
            self, "metadata", MappingProxyType(deepcopy(dict(self.metadata)))
        )


@dataclass(frozen=True)
class ProbeResult:
    status: str
    available: bool
    message: str = ""
    version: str | None = None
    source: str = "adapter"
    warnings: tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.status.strip() or not self.source.strip():
            raise ValueError("probe status and source must be non-empty")
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(
            self, "evidence", MappingProxyType(deepcopy(dict(self.evidence)))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "available": self.available,
            "message": self.message,
            "version": self.version,
            "source": self.source,
            "warnings": list(self.warnings),
            "evidence": deepcopy(dict(self.evidence)),
        }


@dataclass(frozen=True)
class UpdateResult:
    """Bounded, non-secret evidence from a pre-evaluation refresh action."""

    status: str
    message: str
    before_version: str | None = None
    after_version: str | None = None
    source: str = "adapter"
    commands: tuple[tuple[str, ...], ...] = ()
    warnings: tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.status.strip() or not self.source.strip():
            raise ValueError("update status and source must be non-empty")
        commands = tuple(tuple(str(part) for part in command) for command in self.commands)
        if any(not command for command in commands):
            raise ValueError("update commands must be non-empty")
        if any(not part.strip() for command in commands for part in command):
            raise ValueError("update command parts must be non-empty")
        object.__setattr__(self, "commands", commands)
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(
            self, "evidence", MappingProxyType(deepcopy(dict(self.evidence)))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "before_version": self.before_version,
            "after_version": self.after_version,
            "source": self.source,
            "commands": [list(command) for command in self.commands],
            "warnings": list(self.warnings),
            "evidence": deepcopy(dict(self.evidence)),
        }


@dataclass(frozen=True)
class CleanupResult:
    """Bounded evidence from an adapter's compensating cleanup action."""

    status: str
    message: str = ""
    source: str = "adapter"
    commands: tuple[tuple[str, ...], ...] = ()
    warnings: tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.status.strip() or not self.source.strip():
            raise ValueError("cleanup status and source must be non-empty")
        commands = tuple(tuple(str(part) for part in command) for command in self.commands)
        if any(not command for command in commands):
            raise ValueError("cleanup commands must be non-empty")
        if any(not part.strip() for command in commands for part in command):
            raise ValueError("cleanup command parts must be non-empty")
        object.__setattr__(self, "commands", commands)
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(
            self, "evidence", MappingProxyType(deepcopy(dict(self.evidence)))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "source": self.source,
            "commands": [list(command) for command in self.commands],
            "warnings": list(self.warnings),
            "evidence": deepcopy(dict(self.evidence)),
        }


CleanupRunner = Callable[[], CleanupResult]


@dataclass(frozen=True)
class ProviderPreparation:
    """Provider readiness plus the registered action that restores prior state."""

    readiness: ProbeResult
    cleanup_fn: CleanupRunner

    def __post_init__(self) -> None:
        if not callable(self.cleanup_fn):
            raise TypeError("provider preparation cleanup_fn must be callable")

    def cleanup(self) -> CleanupResult:
        return self.cleanup_fn()

    def to_dict(self) -> dict[str, Any]:
        return {"readiness": self.readiness.to_dict(), "cleanup_registered": True}


@dataclass(frozen=True)
class ConnectionProbe:
    """Normalized harness connection/auth observation shared with providers."""

    status: str
    available: bool
    requirements: tuple[str, ...] = ()
    provider_capabilities: tuple[str, ...] = ()
    credential_available: bool | None = None
    message: str = ""
    source: str = "adapter"
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirements", tuple(self.requirements))
        object.__setattr__(
            self, "provider_capabilities", tuple(self.provider_capabilities)
        )
        object.__setattr__(self, "warnings", tuple(self.warnings))


@dataclass(frozen=True)
class ModelOffer:
    provider_model_id: str
    label: str
    source: str = "provider"
    freshness: str = "current"
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelCapabilities:
    known: bool
    modalities: tuple[str, ...] = ()
    reasoning_efforts: tuple[str, ...] = ()
    context_tokens: int | None = None
    tool_use: bool | None = None
    confidence: str = "unknown"


@dataclass(frozen=True)
class CostCapabilities:
    billing_modes: tuple[str, ...] = ()
    evidence_statuses: tuple[str, ...] = ()
    usage_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "billing_modes",
            "evidence_statuses",
            "usage_sources",
        ):
            values = tuple(getattr(self, field_name))
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{field_name} must contain non-empty strings")
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must be unique")
            object.__setattr__(self, field_name, values)


BILLING_MODE_TRACKS = {
    "flat_subscription": "cloud-subscription",
    "metered_api": "cloud-metered",
    "local": "local",
}


def tracks_for_cost_capabilities(
    capabilities: CostCapabilities,
) -> tuple[str, ...]:
    """Return normalized experiment tracks advertised by a provider."""

    return tuple(
        sorted(
            {
                BILLING_MODE_TRACKS[mode]
                for mode in capabilities.billing_modes
                if mode in BILLING_MODE_TRACKS
            }
        )
    )


@dataclass(frozen=True)
class InvocationPlan:
    argv: tuple[str, ...]
    environment_keys: tuple[str, ...] = ()
    model: str = ""
    sandbox: str = "workspace-write"
    working_directory: str | None = None
    stdin_mode: str = "prompt"
    prompt_argument: str = "-"
    evidence_prefix: str = "codex"
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HarnessExecutionContext:
    """Conductor-owned inputs supplied to a harness attempt factory."""

    plan: InvocationPlan
    workspace: Path
    evidence_root: Path
    prompt: str | Callable[[int, Mapping[str, Any] | None], str]
    environment: Mapping[str, str]
    timeout_seconds: float | Callable[[], float]
    secret_values: tuple[str, ...] = ()
    runner: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.plan, InvocationPlan):
            raise TypeError("harness execution plan is required")
        object.__setattr__(self, "workspace", Path(self.workspace))
        object.__setattr__(self, "evidence_root", Path(self.evidence_root))
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))
        object.__setattr__(self, "secret_values", tuple(self.secret_values))
        object.__setattr__(
            self, "metadata", MappingProxyType(deepcopy(dict(self.metadata)))
        )


@dataclass(frozen=True)
class ModelBinding:
    adapter_id: str
    provider_model_id: str
    canonical_id: str
    capabilities: ModelCapabilities
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedSUT:
    harness_id: str
    provider_id: str
    model_id: str
    harness_descriptor: AdapterDescriptor
    provider_descriptor: AdapterDescriptor
    model_descriptor: AdapterDescriptor
    model_binding: ModelBinding
    capabilities: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class HarnessAdapter(Protocol):
    descriptor: AdapterDescriptor

    def detect(self, context: ProbeContext | None = None) -> ProbeResult: ...

    def ensure_current(self, context: ProbeContext | None = None) -> UpdateResult: ...

    def connection_probe(
        self, context: ProbeContext | None = None
    ) -> ConnectionProbe: ...

    def connection_requirements(self) -> tuple[str, ...]: ...

    def credential_reference(self) -> Path | None: ...

    def environment_overrides(
        self, scoped_home: Path, credential_reference: Path | None = None
    ) -> Mapping[str, str]: ...

    def option_schema(self) -> Mapping[str, Any]: ...

    def plan(
        self,
        model: str,
        reasoning_effort: str = "medium",
        sandbox: str = "workspace-write",
        working_directory: str | None = None,
        executable: str | None = None,
        loop: str = "controlled",
    ) -> InvocationPlan: ...

    def create_attempt_executor(self, context: HarnessExecutionContext) -> Any: ...


class ProviderAdapter(Protocol):
    descriptor: AdapterDescriptor

    def detect(self, context: ProbeContext | None = None) -> ProbeResult: ...

    def ensure_current(self, context: ProbeContext | None = None) -> UpdateResult: ...

    def discover_models(
        self, context: ProbeContext | None = None
    ) -> tuple[ModelOffer, ...]: ...

    def option_schema(self) -> Mapping[str, Any]: ...

    def connection_settings(self, context: ProbeContext | None = None) -> Mapping[str, Any]: ...

    def cost_capabilities(self) -> CostCapabilities: ...

    def prepare(
        self, model: str, context: ProbeContext | None = None
    ) -> ProviderPreparation: ...


class ModelAdapter(Protocol):
    descriptor: AdapterDescriptor

    def match(self, offer: ModelOffer) -> bool: ...

    def capabilities(self, offer: ModelOffer) -> ModelCapabilities: ...

    def option_schema(self) -> Mapping[str, Any]: ...

    def resolve(self, model_id: str, offer: ModelOffer) -> ModelBinding: ...
