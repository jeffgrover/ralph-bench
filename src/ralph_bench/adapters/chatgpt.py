"""ChatGPT-managed subscription provider adapter."""

from __future__ import annotations

from .contracts import (
    AdapterDescriptor,
    CostCapabilities,
    ModelOffer,
    CleanupResult,
    ProbeContext,
    ProviderPreparation,
    ProbeResult,
    UpdateResult,
)


class ChatGPTProviderAdapter:
    descriptor = AdapterDescriptor(
        "provider/openai-chatgpt",
        "provider",
        "ChatGPT (subscription)",
        capabilities=(
            "chatgpt-subscription",
            "billing-mode/flat-subscription",
            "cost-evidence/unavailable",
        ),
        detection="harness-auth",
        limitations=("authentication is observed through the selected harness",),
    )

    def detect(self, context: ProbeContext | None = None) -> ProbeResult:
        context = context or ProbeContext()
        authenticated = context.metadata.get("credential_available")
        if authenticated is True:
            return ProbeResult(
                "ok", True,
                "ChatGPT subscription entitlement is available through Codex",
                source="codex login status",
                evidence={"credential_available": True},
            )
        if authenticated is False:
            return ProbeResult(
                "unauthorized", False,
                "ChatGPT subscription is not authenticated; run `codex login`",
                source="codex login status",
                evidence={"credential_available": False},
            )
        return ProbeResult(
            "partial", False,
            "ChatGPT entitlement requires Codex authentication preflight",
            source="adapter",
            warnings=("provider detection is dependent on a harness auth probe",),
        )

    def discover_models(
        self, context: ProbeContext | None = None
    ) -> tuple[ModelOffer, ...]:
        return (
            ModelOffer(
                "gpt-5.6-luna",
                "GPT-5.6 Luna",
                source="Codex-supported P0 descriptor",
                freshness="static",
                capabilities=("reasoning", "tool-use"),
            ),
        )

    def ensure_current(self, context: ProbeContext | None = None) -> UpdateResult:
        return UpdateResult(
            "not-applicable",
            "ChatGPT provider is managed by the selected harness",
            source="provider/openai-chatgpt",
            evidence={"management": "harness"},
        )

    def prepare(
        self, model: str, context: ProbeContext | None = None
    ) -> ProviderPreparation:
        readiness = ProbeResult(
            "ready",
            True,
            "ChatGPT provider requires no local runtime preparation",
            source="provider/openai-chatgpt",
            evidence={"model": model, "management": "harness"},
        )
        return ProviderPreparation(
            readiness,
            lambda: CleanupResult(
                "not-applicable",
                "ChatGPT provider has no local state to restore",
                source="provider/openai-chatgpt",
            ),
        )

    def option_schema(self) -> dict[str, object]:
        return {}

    def connection_settings(self, context: ProbeContext | None = None) -> dict[str, object]:
        return {}

    def cost_capabilities(self) -> CostCapabilities:
        return CostCapabilities(
            billing_modes=("flat_subscription",),
            evidence_statuses=("unavailable",),
            usage_sources=("codex-events",),
        )
