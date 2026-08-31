"""Independent harness, provider, and model adapter contracts."""

from .chatgpt import ChatGPTProviderAdapter
from .codex import CodexHarnessAdapter
from .lmstudio import LMStudioProviderAdapter
from .codex_execution import (
    CodexAttemptExecutor,
    CodexExecutionError,
    CodexStreamSummary,
    ProcessExecutionResult,
    SubprocessExecutor,
    credential_secret_values,
    parse_codex_jsonl,
)
from .contracts import (
    AdapterDescriptor,
    BILLING_MODE_TRACKS,
    CleanupResult,
    CleanupRunner,
    ConnectionProbe,
    CostCapabilities,
    HarnessAdapter,
    HarnessExecutionContext,
    InvocationPlan,
    ModelAdapter,
    ModelBinding,
    ModelCapabilities,
    ModelOffer,
    ProbeContext,
    ProbeResult,
    ProviderPreparation,
    ProcessResult,
    ProcessRunner,
    ProviderAdapter,
    ResolvedSUT,
    UpdateResult,
)
from .models import GenericModelAdapter, LunaModelAdapter
from .pi import PiHarnessAdapter
from .pi_execution import PiAttemptExecutor, PiExecutionError, PiStreamSummary, parse_pi_jsonl
from .registry import AdapterRegistry, built_in_registry
from .resolver import ResolutionError, resolve_sut

__all__ = [
    "AdapterDescriptor",
    "AdapterRegistry",
    "BILLING_MODE_TRACKS",
    "ChatGPTProviderAdapter",
    "CleanupResult",
    "CleanupRunner",
    "CodexHarnessAdapter",
    "CodexAttemptExecutor",
    "CodexExecutionError",
    "CodexStreamSummary",
    "ConnectionProbe",
    "CostCapabilities",
    "GenericModelAdapter",
    "HarnessAdapter",
    "HarnessExecutionContext",
    "InvocationPlan",
    "LunaModelAdapter",
    "LMStudioProviderAdapter",
    "ModelAdapter",
    "ModelBinding",
    "ModelCapabilities",
    "ModelOffer",
    "ProbeContext",
    "ProbeResult",
    "ProviderPreparation",
    "ProcessResult",
    "ProcessExecutionResult",
    "ProcessRunner",
    "PiHarnessAdapter",
    "PiAttemptExecutor",
    "PiExecutionError",
    "PiStreamSummary",
    "ProviderAdapter",
    "ResolutionError",
    "ResolvedSUT",
    "SubprocessExecutor",
    "UpdateResult",
    "built_in_registry",
    "credential_secret_values",
    "parse_codex_jsonl",
    "parse_pi_jsonl",
    "resolve_sut",
]
