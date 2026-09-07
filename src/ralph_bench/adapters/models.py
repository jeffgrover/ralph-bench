"""Declarative P0 model descriptors and conservative generic fallback."""

from __future__ import annotations

from .contracts import (
    AdapterDescriptor,
    ModelBinding,
    ModelCapabilities,
    ModelOffer,
    REASONING_EFFORTS,
)


class KnownOpenAIModelAdapter:
    """Known Codex model descriptors with the same P0 capability contract."""

    def __init__(self, model_id: str, label: str) -> None:
        self.model_id = model_id
        self.descriptor = AdapterDescriptor(
            f"model/{model_id}",
            "model",
            label,
            capabilities=("reasoning", "tool-use"),
            detection="descriptor",
        )

    def match(self, offer: ModelOffer) -> bool:
        return offer.provider_model_id == self.model_id

    def capabilities(self, offer: ModelOffer) -> ModelCapabilities:
        return ModelCapabilities(
            True,
            ("text",),
            REASONING_EFFORTS,
            tool_use=True,
            confidence="declared",
        )

    def resolve(self, model_id: str, offer: ModelOffer) -> ModelBinding:
        if not self.match(offer):
            raise ValueError(f"model offer does not match {self.descriptor.adapter_id}")
        return ModelBinding(
            self.descriptor.adapter_id,
            offer.provider_model_id,
            self.model_id,
            self.capabilities(offer),
        )


class LunaModelAdapter(KnownOpenAIModelAdapter):
    def __init__(self) -> None:
        super().__init__("gpt-5.6-luna", "GPT-5.6 Luna")


class TerraModelAdapter(KnownOpenAIModelAdapter):
    def __init__(self) -> None:
        super().__init__("gpt-5.6-terra", "GPT-5.6 Terra")


class SolModelAdapter(KnownOpenAIModelAdapter):
    def __init__(self) -> None:
        super().__init__("gpt-5.6-sol", "GPT-5.6 Sol")


class AstraModelAdapter(KnownOpenAIModelAdapter):
    def __init__(self) -> None:
        super().__init__("gpt-6-astra", "GPT-6 Astra")


class GenericModelAdapter:
    descriptor = AdapterDescriptor(
        "model/generic",
        "model",
        "Generic model",
        detection="manual",
        limitations=("unknown capabilities are conservative",),
    )

    def match(self, offer: ModelOffer) -> bool:
        return True

    def capabilities(self, offer: ModelOffer) -> ModelCapabilities:
        return ModelCapabilities(False, confidence="unknown")

    def resolve(self, model_id: str, offer: ModelOffer) -> ModelBinding:
        return ModelBinding(
            self.descriptor.adapter_id,
            offer.provider_model_id,
            model_id,
            self.capabilities(offer),
            ("model capabilities are unknown",),
        )
