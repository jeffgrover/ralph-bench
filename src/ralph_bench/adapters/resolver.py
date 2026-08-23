"""Capability-based adapter composition."""

from __future__ import annotations

from dataclasses import dataclass

from ..experiments import Experiment
from .contracts import ModelOffer, ProbeContext, ResolvedSUT
from .registry import AdapterRegistry, built_in_registry


@dataclass(frozen=True)
class ResolutionIssue:
    code: str
    message: str


class ResolutionError(ValueError):
    def __init__(self, message: str, *, code: str = "incompatible") -> None:
        self.issue = ResolutionIssue(code, message)
        super().__init__(message)


def resolve_sut(
    experiment: Experiment,
    registry: AdapterRegistry | None = None,
    *,
    context: ProbeContext | None = None,
) -> ResolvedSUT:
    registry = registry or built_in_registry()
    context = context or ProbeContext()
    if experiment.client_options.executable is not None:
        context = ProbeContext(
            timeout_seconds=context.timeout_seconds,
            executable=experiment.client_options.executable,
            process_runner=context.process_runner,
            metadata=context.metadata,
        )
    try:
        harness = registry.get("harness", experiment.client)
        provider = registry.get("provider", experiment.provider)
    except KeyError as exc:
        raise ResolutionError(str(exc), code="adapter-not-found") from exc

    detected = harness.detect(context)
    if not detected.available and detected.status not in {"partial", "manual"}:
        raise ResolutionError(f"harness unavailable: {detected.message}", code="harness-unavailable")

    connection = harness.connection_probe(context)
    provider_context = ProbeContext(
        context.timeout_seconds,
        context.executable,
        context.process_runner,
        {**context.metadata, "credential_available": connection.credential_available},
    )
    provider_probe = provider.detect(provider_context)
    provider_capabilities = set(provider.descriptor.capabilities)
    missing = sorted(set(connection.requirements) - provider_capabilities)
    if missing:
        raise ResolutionError(
            "provider does not expose required connection capability(ies): " + ", ".join(missing),
            code="connection-incompatible",
        )
    if not connection.available:
        raise ResolutionError(
            f"harness connection unavailable: {connection.message}", code="connection-unavailable"
        )
    if not provider_probe.available:
        raise ResolutionError(f"provider unavailable: {provider_probe.message}", code="provider-unavailable")
    if experiment.cost is not None:
        cost_capabilities = provider.cost_capabilities()
        if experiment.cost.policy not in cost_capabilities.policies:
            raise ResolutionError(
                f"provider does not support requested cost policy {experiment.cost.policy!r}",
                code="cost-incompatible",
            )

    offers = provider.discover_models(provider_context)
    matching = [offer for offer in offers if offer.provider_model_id == experiment.model]
    if not matching:
        matching = [ModelOffer(experiment.model, experiment.model, source="manual", freshness="unknown")]
    offer = matching[0]
    candidates = [
        adapter for adapter in registry.models.values()
        if adapter.descriptor.adapter_id != "model/generic" and adapter.match(offer)
    ]
    model = candidates[0] if candidates else registry.get("model", "model/generic")
    model_capabilities = model.capabilities(offer)
    requested_effort = experiment.client_options.reasoning_effort
    if model_capabilities.known and requested_effort not in model_capabilities.reasoning_efforts:
        raise ResolutionError(
            f"requested reasoning effort {requested_effort!r} is not supported by model {experiment.model!r}",
            code="effort-incompatible",
        )
    binding = model.resolve(experiment.model, offer)
    capabilities = tuple(sorted(
        set(harness.descriptor.capabilities)
        | provider_capabilities
        | set(model_capabilities.reasoning_efforts)
    ))
    warnings = (
        tuple(detected.warnings)
        + tuple(connection.warnings)
        + tuple(provider_probe.warnings)
        + tuple(binding.warnings)
    )
    if offer.freshness == "static":
        warnings += (
            "model availability comes from a static P0 descriptor; live entitlement "
            "must be confirmed at invocation preflight",
        )
    return ResolvedSUT(
        harness.descriptor.adapter_id,
        provider.descriptor.adapter_id,
        model.descriptor.adapter_id,
        harness.descriptor,
        provider.descriptor,
        model.descriptor,
        binding,
        capabilities,
        warnings,
    )
