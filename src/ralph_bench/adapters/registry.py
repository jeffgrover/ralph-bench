"""Explicit built-in adapter registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .chatgpt import ChatGPTProviderAdapter
from .codex import CodexHarnessAdapter
from .llama_swap import LlamaSwapProviderAdapter
from .lmstudio import LMStudioProviderAdapter
from .pi import PiHarnessAdapter
from .contracts import HarnessAdapter, ModelAdapter, ProviderAdapter
from .models import (
    AstraModelAdapter,
    GenericModelAdapter,
    LunaModelAdapter,
    SolModelAdapter,
    TerraModelAdapter,
)


@dataclass
class AdapterRegistry:
    harnesses: dict[str, HarnessAdapter]
    providers: dict[str, ProviderAdapter]
    models: dict[str, ModelAdapter]

    def __post_init__(self) -> None:
        for family, entries in (
            ("harness", self.harnesses),
            ("provider", self.providers),
            ("model", self.models),
        ):
            for key, adapter in entries.items():
                descriptor = getattr(adapter, "descriptor", None)
                if descriptor is None or descriptor.adapter_id != key or descriptor.family != family:
                    raise ValueError(f"invalid {family} adapter registration: {key}")

    def all(self) -> tuple[HarnessAdapter | ProviderAdapter | ModelAdapter, ...]:
        return tuple(self.harnesses.values()) + tuple(self.providers.values()) + tuple(self.models.values())

    def get(self, family: str, adapter_id: str) -> Any:
        entries = {"harness": self.harnesses, "provider": self.providers, "model": self.models}.get(family)
        if entries is None:
            raise KeyError(f"unknown adapter family: {family}")
        if adapter_id in entries:
            return entries[adapter_id]
        try:
            return entries[f"{family}/{adapter_id}"]
        except KeyError as exc:
            raise KeyError(f"unknown {family} adapter: {adapter_id}") from exc


def built_in_registry(
    *,
    codex: CodexHarnessAdapter | None = None,
    pi: PiHarnessAdapter | None = None,
    llama_swap: LlamaSwapProviderAdapter | None = None,
    lmstudio: LMStudioProviderAdapter | None = None,
) -> AdapterRegistry:
    harness = codex or CodexHarnessAdapter()
    pi_harness = pi or PiHarnessAdapter()
    provider = ChatGPTProviderAdapter()
    swap_provider = llama_swap or LlamaSwapProviderAdapter()
    local_provider = lmstudio or LMStudioProviderAdapter()
    luna = LunaModelAdapter()
    terra = TerraModelAdapter()
    sol = SolModelAdapter()
    astra = AstraModelAdapter()
    generic = GenericModelAdapter()
    return AdapterRegistry(
        {
            harness.descriptor.adapter_id: harness,
            pi_harness.descriptor.adapter_id: pi_harness,
        },
        {
            provider.descriptor.adapter_id: provider,
            swap_provider.descriptor.adapter_id: swap_provider,
            local_provider.descriptor.adapter_id: local_provider,
        },
        {
            luna.descriptor.adapter_id: luna,
            terra.descriptor.adapter_id: terra,
            sol.descriptor.adapter_id: sol,
            astra.descriptor.adapter_id: astra,
            generic.descriptor.adapter_id: generic,
        },
    )
