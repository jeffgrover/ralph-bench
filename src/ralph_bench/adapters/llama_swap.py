"""llama-swap local inference provider boundary.

llama-swap exposes one OpenAI-compatible proxy and loads the requested model
 lazily on the first completion request.  The adapter therefore verifies the
 proxy and the selected model advertisement during preflight without issuing
 a model invocation outside the harness evidence stream.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import shutil
import subprocess
from typing import Any, Callable, Mapping
from urllib.error import URLError
from urllib.request import Request, urlopen

from .contracts import (
    AdapterDescriptor,
    CleanupResult,
    CostCapabilities,
    ModelOffer,
    ProbeContext,
    ProbeResult,
    ProcessResult,
    ProviderPreparation,
    UpdateResult,
)


_VERSION_PATTERN = re.compile(
    r"^version:\s*(?P<version>[0-9A-Za-z._-]+(?:\s+\([^)]*\))?)(?:,.*)?$"
)


@dataclass(frozen=True)
class _HttpResult:
    status: int
    body: str = ""
    error: str = ""
    timed_out: bool = False


def _default_runner(argv: tuple[str, ...], timeout: float) -> ProcessResult:
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return ProcessResult(124, stdout, stderr, True)
    return ProcessResult(result.returncode, result.stdout, result.stderr)


def _default_http_runner(method: str, url: str, timeout: float) -> _HttpResult:
    try:
        request = Request(url, method=method, headers={"Accept": "application/json"})
        with urlopen(request, timeout=timeout) as response:
            body = response.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
            return _HttpResult(response.status, body)
    except TimeoutError:
        return _HttpResult(0, timed_out=True, error="request timed out")
    except URLError as exc:
        return _HttpResult(0, error=str(exc.reason))
    except OSError as exc:
        return _HttpResult(0, error=str(exc))


def _json_object(text: str) -> object | None:
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None


def _model_offers(value: object) -> tuple[ModelOffer, ...]:
    items: object = value
    if isinstance(value, Mapping) and isinstance(value.get("data"), list):
        items = value["data"]
    if not isinstance(items, list):
        return ()
    offers: list[ModelOffer] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str):
            model_id = item.strip()
            label = model_id
        elif isinstance(item, Mapping):
            model_id = next(
                (
                    str(item[key]).strip()
                    for key in ("id", "model", "name")
                    if isinstance(item.get(key), str) and item[key].strip()
                ),
                "",
            )
            label = next(
                (
                    str(item[key]).strip()
                    for key in ("name", "id")
                    if isinstance(item.get(key), str) and item[key].strip()
                ),
                model_id,
            )
        else:
            continue
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        offers.append(
            ModelOffer(
                model_id,
                label or model_id,
                source="llama-swap GET /v1/models",
                freshness="current",
                capabilities=("local", "openai-compatible"),
            )
        )
    return tuple(offers)


def _running_ids(value: object) -> tuple[str, ...]:
    items: object = value
    if isinstance(value, Mapping):
        for key in ("models", "data", "running"):
            if isinstance(value.get(key), list):
                items = value[key]
                break
    if not isinstance(items, list):
        return ()
    result: list[str] = []
    for item in items:
        if isinstance(item, str):
            model_id = item.strip()
        elif isinstance(item, Mapping):
            model_id = next(
                (
                    str(item[key]).strip()
                    for key in ("id", "model", "name")
                    if isinstance(item.get(key), str) and item[key].strip()
                ),
                "",
            )
        else:
            model_id = ""
        if model_id and model_id not in result:
            result.append(model_id)
    return tuple(result)


class LlamaSwapProviderAdapter:
    descriptor = AdapterDescriptor(
        "provider/llama-swap",
        "provider",
        "llama-swap (Intel local)",
        capabilities=(
            "local-provider",
            "openai-compatible",
            "billing-mode/local",
            "cost-evidence/not-applicable",
        ),
        detection="executable-and-http-proxy",
        limitations=(
            "llama-swap has no provider update command; binary freshness is recorded",
            "model loading is lazy and begins with the first Pi completion request",
        ),
    )

    def __init__(
        self,
        executable: str | None = None,
        process_runner: Callable[[tuple[str, ...], float], ProcessResult] | None = None,
        http_runner: Callable[[str, str, float], _HttpResult] | None = None,
    ) -> None:
        self.executable = executable or os.environ.get("LLAMA_SWAP_EXECUTABLE", "llama-swap")
        self._runner = process_runner or _default_runner
        self._http_runner = http_runner or _default_http_runner

    def _run(self, argv: tuple[str, ...], context: ProbeContext) -> ProcessResult:
        return (context.process_runner or self._runner)(argv, context.timeout_seconds)

    def _executable(self, context: ProbeContext) -> str:
        value = context.metadata.get("provider_executable", self.executable)
        return value.strip() if isinstance(value, str) and value.strip() else self.executable

    def _endpoint(self, context: ProbeContext) -> str:
        value = context.metadata.get(
            "provider_endpoint", os.environ.get("LLAMA_SWAP_URL", "http://127.0.0.1:8080/v1")
        )
        if not isinstance(value, str) or not value.strip():
            value = "http://127.0.0.1:8080/v1"
        return value.rstrip("/")

    def _root_endpoint(self, context: ProbeContext) -> str:
        endpoint = self._endpoint(context)
        return endpoint[:-3] if endpoint.endswith("/v1") else endpoint

    def _get(self, url: str, context: ProbeContext) -> _HttpResult:
        return self._http_runner("GET", url, context.timeout_seconds)

    def _version(self, context: ProbeContext) -> ProbeResult:
        executable = self._executable(context)
        if context.process_runner is None and shutil.which(executable) is None:
            return ProbeResult(
                "unavailable", False, f"{executable!r} was not found", source="llama-swap -version"
            )
        result = self._run((executable, "-version"), context)
        if result.timed_out:
            return ProbeResult("timed-out", False, "llama-swap -version timed out", source="llama-swap -version")
        if result.returncode != 0:
            return ProbeResult("failed", False, "llama-swap -version failed", source="llama-swap -version")
        version = next(
            (
                match.group("version")
                for line in (result.stdout + "\n" + result.stderr).splitlines()
                if (match := _VERSION_PATTERN.fullmatch(line.strip())) is not None
            ),
            None,
        )
        if version is None:
            return ProbeResult(
                "failed", False, "llama-swap -version returned an unrecognized version format",
                source="llama-swap -version",
            )
        return ProbeResult(
            "ok", True, "llama-swap binary detected", version=version,
            source="llama-swap -version",
            evidence={"executable": executable, "resolved_executable": shutil.which(executable) or executable},
        )

    def detect(self, context: ProbeContext | None = None) -> ProbeResult:
        context = context or ProbeContext()
        version = self._version(context)
        if not version.available:
            return version
        root = self._root_endpoint(context)
        health = self._get(f"{root}/health", context)
        if health.timed_out or health.status != 200:
            return ProbeResult(
                "partial", False, "llama-swap binary is present but proxy health is unavailable",
                version=version.version, source="GET /health",
                warnings=("start llama-swap before evaluation",),
                evidence={"executable": version.evidence.get("executable"), "endpoint": root},
            )
        models = self._get(f"{self._endpoint(context)}/models", context)
        offers = _model_offers(_json_object(models.body)) if models.status == 200 else ()
        if not offers:
            return ProbeResult(
                "partial", False, "llama-swap is healthy but its OpenAI model list is unavailable",
                version=version.version, source="GET /v1/models",
                evidence={"executable": version.evidence.get("executable"), "endpoint": self._endpoint(context)},
            )
        return ProbeResult(
            "ok", True, "llama-swap proxy is healthy", version=version.version,
            source="GET /health and GET /v1/models",
            evidence={
                "executable": version.evidence.get("executable"),
                "endpoint": self._endpoint(context),
                "advertised_models": [offer.provider_model_id for offer in offers],
            },
        )

    def ensure_current(self, context: ProbeContext | None = None) -> UpdateResult:
        context = context or ProbeContext()
        before = self._version(context)
        executable = self._executable(context)
        command = (executable, "-version")
        if not before.available:
            return UpdateResult(
                "unavailable", f"llama-swap freshness cannot be verified: {before.message}",
                source="llama-swap -version", commands=(command,), evidence={"executable": executable},
            )
        return UpdateResult(
            "current", "llama-swap version recorded; no in-run update is supported",
            before_version=before.version, after_version=before.version,
            source="llama-swap -version", commands=(command,),
            warnings=("llama-swap and llama-server are managed outside rb; no update was attempted",),
            evidence={
                "executable": executable,
                "resolved_executable": before.evidence.get("resolved_executable", executable),
                "update_supported": False,
                "endpoint": self._endpoint(context),
            },
        )

    def discover_models(self, context: ProbeContext | None = None) -> tuple[ModelOffer, ...]:
        context = context or ProbeContext()
        result = self._get(f"{self._endpoint(context)}/models", context)
        if result.timed_out or result.status != 200:
            return ()
        return _model_offers(_json_object(result.body))

    def prepare(self, model: str, context: ProbeContext | None = None) -> ProviderPreparation:
        context = context or ProbeContext()
        endpoint = self._endpoint(context)
        root = self._root_endpoint(context)
        if not model.strip():
            return ProviderPreparation(
                ProbeResult("failed", False, "llama-swap model selection is empty", source="provider/llama-swap"),
                lambda: CleanupResult("not-applicable", "No llama-swap state was changed", source="provider/llama-swap"),
            )
        models = self._get(f"{endpoint}/models", context)
        offers = _model_offers(_json_object(models.body)) if models.status == 200 else ()
        if not any(offer.provider_model_id == model for offer in offers):
            return ProviderPreparation(
                ProbeResult(
                    "not-ready", False, f"selected model {model!r} is not advertised by llama-swap",
                    source="GET /v1/models", evidence={"endpoint": endpoint, "model": model},
                ),
                lambda: CleanupResult("not-applicable", "No llama-swap state was changed", source="provider/llama-swap"),
            )
        running_response = self._get(f"{root}/running", context)
        running = _running_ids(_json_object(running_response.body)) if running_response.status == 200 else ()
        readiness = ProbeResult(
            "ready", True,
            "llama-swap proxy and selected model are ready; model loading is lazy",
            source="GET /health, GET /v1/models, GET /running",
            warnings=("the selected llama-server loads on the first Pi completion request",),
            evidence={
                "endpoint": endpoint,
                "model": model,
                "advertised_models": [offer.provider_model_id for offer in offers],
                "running_models": list(running),
                "provider_mutation": "none",
                "lazy_model_load": True,
            },
        )
        return ProviderPreparation(
            readiness,
            lambda: CleanupResult(
                "not-applicable",
                "llama-swap owns model lifecycle; no provider state was changed by preflight",
                source="provider/llama-swap",
                evidence={"endpoint": endpoint, "model": model, "cleanup": "proxy-ttl"},
            ),
        )

    def option_schema(self) -> dict[str, object]:
        return {"endpoint": {"default": "http://127.0.0.1:8080/v1"}}

    def connection_settings(self, context: ProbeContext | None = None) -> dict[str, object]:
        context = context or ProbeContext()
        return {
            "native_name": "local-b70",
            "base_url": self._endpoint(context),
            "api": "openai-completions",
            "api_key": "sk-local",
            "credential_mode": "local-placeholder",
            "context_window": 131072,
            "max_tokens": 32768,
        }

    def cost_capabilities(self) -> CostCapabilities:
        return CostCapabilities(
            billing_modes=("local",),
            evidence_statuses=("unavailable",),
            usage_sources=("provider-local",),
        )


__all__ = ["LlamaSwapProviderAdapter"]
