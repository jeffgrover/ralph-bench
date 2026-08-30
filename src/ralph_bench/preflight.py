"""Generic current-toolchain and provider-readiness preflight."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .adapters import (
    AdapterRegistry,
    CleanupResult,
    ProbeContext,
    ResolvedSUT,
)
from .adapters.contracts import CleanupRunner
from .experiments import Experiment


class PreflightError(RuntimeError):
    """The selected toolchain or provider is not ready for evaluation."""

    def __init__(
        self, message: str, *, cleanup_fn: CleanupRunner | None = None
    ) -> None:
        super().__init__(message)
        self.cleanup_fn = cleanup_fn

    def cleanup(self) -> CleanupResult:
        if self.cleanup_fn is None:
            return CleanupResult(
                "not-applicable",
                "No provider state was changed",
                source="toolchain preflight",
            )
        return self.cleanup_fn()


class PreflightSession:
    """Successful preflight evidence and its provider rollback registration."""

    def __init__(self, evidence: dict[str, Any], cleanup_fn: CleanupRunner) -> None:
        self.evidence = evidence
        self._cleanup_fn = cleanup_fn

    def cleanup(self) -> CleanupResult:
        return self._cleanup_fn()


_OK_UPDATE_STATUSES = frozenset({"current", "updated", "not-applicable"})


def context_for_experiment(
    experiment: Experiment, context: ProbeContext | None = None
) -> ProbeContext:
    context = context or ProbeContext()
    executable = experiment.client_options.executable
    if executable is None or executable == context.executable:
        return context
    return replace(context, executable=executable)


def _require_update(component: str, update: Any) -> None:
    if update.status not in _OK_UPDATE_STATUSES:
        raise PreflightError(f"{component} current-toolchain preflight failed: {update.message}")


def run_sut_preflight(
    experiment: Experiment,
    sut: ResolvedSUT,
    registry: AdapterRegistry,
    *,
    context: ProbeContext | None = None,
) -> PreflightSession:
    """Refresh selected tools, re-check the connection, and verify readiness."""

    harness_context = context_for_experiment(experiment, context)
    harness = registry.get("harness", sut.harness_id)
    provider = registry.get("provider", sut.provider_id)
    harness_update = harness.ensure_current(harness_context)
    _require_update("harness", harness_update)

    connection = harness.connection_probe(harness_context)
    provider_context = replace(
        harness_context,
        metadata={
            **harness_context.metadata,
            "credential_available": connection.credential_available,
        },
    )
    provider_update = provider.ensure_current(provider_context)
    _require_update("provider", provider_update)
    provider_probe = provider.detect(provider_context)
    if not connection.available:
        raise PreflightError(f"harness connection preflight failed: {connection.message}")
    if not provider_probe.available:
        raise PreflightError(f"provider preflight failed: {provider_probe.message}")
    preparation = provider.prepare(experiment.model, provider_context)
    if not preparation.readiness.available:
        raise PreflightError(
            f"provider readiness preflight failed: {preparation.readiness.message}",
            cleanup_fn=preparation.cleanup,
        )
    evidence = {
        "schema_version": "toolchain-preflight/v1",
        "status": "ready",
        "harness": {
            "adapter_id": sut.harness_id,
            "update": harness_update.to_dict(),
            "connection": {
                "status": connection.status,
                "available": connection.available,
                "source": connection.source,
                "credential_available": connection.credential_available,
                "warnings": list(connection.warnings),
            },
        },
        "provider": {
            "adapter_id": sut.provider_id,
            "update": provider_update.to_dict(),
            "probe": provider_probe.to_dict(),
            "readiness": preparation.readiness.to_dict(),
            "cleanup_registered": True,
        },
    }
    return PreflightSession(evidence, preparation.cleanup)


__all__ = [
    "PreflightError",
    "PreflightSession",
    "context_for_experiment",
    "run_sut_preflight",
]
