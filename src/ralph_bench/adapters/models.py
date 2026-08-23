"""Declarative P0 model descriptors and conservative generic fallback."""

from __future__ import annotations

from .contracts import AdapterDescriptor, ModelBinding, ModelCapabilities, ModelOffer


class LunaModelAdapter:
    descriptor = AdapterDescriptor(
        "model/gpt-5.6-luna",
        "model",
        "GPT-5.6 Luna",
        capabilities=("reasoning", "tool-use"),
        detection="descriptor",
    )

    def match(self, offer: ModelOffer) -> bool:
        return offer.provider_model_id == "gpt-5.6-luna"

    def capabilities(self, offer: ModelOffer) -> ModelCapabilities:
        return ModelCapabilities(
            True,
            ("text",),
            ("none", "low", "medium", "high", "xhigh", "max"),
            tool_use=True,
            confidence="declared",
        )

    def option_schema(self) -> dict[str, object]:
        return {
            "reasoning_effort": {
                "values": ("none", "low", "medium", "high", "xhigh", "max")
            }
        }

    def resolve(self, model_id: str, offer: ModelOffer) -> ModelBinding:
        if not self.match(offer):
            raise ValueError(f"model offer does not match {self.descriptor.adapter_id}")
        return ModelBinding(
            self.descriptor.adapter_id,
            offer.provider_model_id,
            "gpt-5.6-luna",
            self.capabilities(offer),
        )


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

    def option_schema(self) -> dict[str, object]:
        return {}

    def resolve(self, model_id: str, offer: ModelOffer) -> ModelBinding:
        return ModelBinding(
            self.descriptor.adapter_id,
            offer.provider_model_id,
            model_id,
            self.capabilities(offer),
            ("model capabilities are unknown",),
        )
