"""ChatGPT-managed subscription provider adapter."""

from __future__ import annotations

from .contracts import (
    AdapterDescriptor,
    CostCapabilities,
    ModelOffer,
    ProbeContext,
    ProbeResult,
)


class ChatGPTProviderAdapter:
    descriptor = AdapterDescriptor(
        "provider/openai-chatgpt",
        "provider",
        "ChatGPT (subscription)",
        capabilities=("chatgpt-subscription", "flat-subscription-attempt-pool/v1"),
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

    def option_schema(self) -> dict[str, object]:
        return {"subscription_profile": {"type": "named-reference", "secret": False}}

    def cost_capabilities(self) -> CostCapabilities:
        return CostCapabilities(
            ("flat-subscription-attempt-pool/v1",),
            ("conductor-invocation-event",),
            ("flat-subscription",),
        )
