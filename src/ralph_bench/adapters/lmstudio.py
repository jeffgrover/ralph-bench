"""LM Studio local inference provider boundary."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any, Callable, Mapping

from .contracts import (
    AdapterDescriptor,
    CleanupResult,
    CostCapabilities,
    ModelOffer,
    ProbeContext,
    ProviderPreparation,
    ProbeResult,
    ProcessResult,
    UpdateResult,
)


_VERSION_PATTERN = re.compile(r"^(?:CLI commit:\s*)?(?P<version>[0-9A-Za-z._-]+)$")


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


def _json_object(text: str) -> object | None:
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None


def _server_running(value: object) -> bool | None:
    if not isinstance(value, Mapping):
        return None
    for key in ("running", "isRunning", "serverRunning"):
        if isinstance(value.get(key), bool):
            return bool(value[key])
    status = value.get("status") or value.get("state")
    if isinstance(status, str):
        lowered = status.casefold()
        if lowered in {"running", "started", "ready", "online"}:
            return True
        if lowered in {"stopped", "starting", "stopping", "offline", "not_running"}:
            return False
    return None


def _loaded_model_ids(value: object) -> tuple[str, ...]:
    items: object = value
    if isinstance(value, Mapping):
        for key in ("models", "loadedModels", "data"):
            if isinstance(value.get(key), list):
                items = value[key]
                break
    if not isinstance(items, list):
        return ()
    result: list[str] = []
    for item in items:
        if isinstance(item, str):
            candidate = item
        elif isinstance(item, Mapping):
            candidate = next(
                (
                    str(item[key])
                    for key in ("id", "modelKey", "model", "identifier", "path")
                    if isinstance(item.get(key), str) and item[key].strip()
                ),
                "",
            )
        else:
            candidate = ""
        if candidate and candidate not in result:
            result.append(candidate)
    return tuple(result)


def _model_matches(requested: str, loaded: str) -> bool:
    return (
        requested == loaded
        or loaded.endswith("/" + requested)
        or requested.endswith("/" + loaded)
    )


def _model_offers(value: object) -> tuple[ModelOffer, ...]:
    items: object = value
    if isinstance(value, Mapping):
        for key in ("models", "data"):
            if isinstance(value.get(key), list):
                items = value[key]
                break
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
                    for key in ("modelKey", "id", "identifier", "path", "name")
                    if isinstance(item.get(key), str) and item[key].strip()
                ),
                "",
            )
            label = next(
                (
                    str(item[key]).strip()
                    for key in ("displayName", "name", "id", "modelKey")
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
                source="lms ls --llm --json",
                freshness="current",
                capabilities=("local",),
            )
        )
    return tuple(offers)


class LMStudioProviderAdapter:
    descriptor = AdapterDescriptor(
        "provider/lm-studio",
        "provider",
        "LM Studio",
        capabilities=(
            "local-provider",
            "openai-compatible",
            "billing-mode/local",
            "cost-evidence/not-applicable",
        ),
        detection="executable-and-server",
        limitations=(
            "the lms CLI cannot update the LM Studio desktop application",
            "desktop-app freshness is not observable through the lms CLI",
        ),
    )

    def __init__(
        self,
        executable: str = "lms",
        process_runner: Callable[[tuple[str, ...], float], ProcessResult] | None = None,
    ) -> None:
        self.executable = executable
        self._runner = process_runner or _default_runner

    def _run(self, argv: tuple[str, ...], context: ProbeContext) -> ProcessResult:
        return (context.process_runner or self._runner)(argv, context.timeout_seconds)

    def _version(self, context: ProbeContext) -> ProbeResult:
        executable = context.metadata.get("provider_executable", self.executable)
        if not isinstance(executable, str) or not executable.strip():
            executable = self.executable
        if context.process_runner is None and shutil.which(executable) is None:
            return ProbeResult(
                "unavailable", False, f"{executable!r} was not found", source="lms --version"
            )
        result = self._run((executable, "--version"), context)
        if result.timed_out:
            return ProbeResult("timed-out", False, "lms --version timed out", source="lms --version")
        if result.returncode != 0:
            return ProbeResult("failed", False, "lms --version failed", source="lms --version")
        version = next(
            (
                match.group("version")
                for line in result.stdout.splitlines()
                if (match := _VERSION_PATTERN.fullmatch(line.strip())) is not None
            ),
            None,
        )
        if version is None:
            return ProbeResult(
                "failed", False, "lms --version returned an unrecognized version format",
                source="lms --version",
            )
        return ProbeResult(
            "ok", True, "LM Studio CLI detected", version=version,
            source="lms --version",
            evidence={
                "executable": executable,
                "resolved_executable": shutil.which(executable) or executable,
            },
        )

    def detect(self, context: ProbeContext | None = None) -> ProbeResult:
        context = context or ProbeContext()
        version = self._version(context)
        if not version.available:
            return version
        executable = str(version.evidence.get("executable", self.executable))
        status_result = self._run((executable, "server", "status", "--json"), context)
        if status_result.timed_out:
            return ProbeResult(
                "partial", True, "LM Studio CLI is installed but server status timed out",
                version=version.version, source="lms server status --json",
                warnings=("provider server readiness must be confirmed before invocation",),
                evidence={"executable": executable},
            )
        status = _json_object(status_result.stdout)
        running = _server_running(status)
        if status_result.returncode != 0 or running is None:
            return ProbeResult(
                "partial", True, "LM Studio CLI is installed; server readiness is unknown",
                version=version.version, source="lms server status --json",
                warnings=("provider server readiness must be confirmed before invocation",),
                evidence={"executable": executable},
            )
        if not running:
            return ProbeResult(
                "partial", True, "LM Studio CLI is installed but the server is not running",
                version=version.version, source="lms server status --json",
                warnings=("start LM Studio server before evaluation",),
                evidence={"executable": executable, "server_running": False},
            )
        return ProbeResult(
            "ok", True, "LM Studio server is running", version=version.version,
            source="lms server status --json",
            evidence={"executable": executable, "server_running": True},
        )

    def ensure_current(self, context: ProbeContext | None = None) -> UpdateResult:
        context = context or ProbeContext()
        before = self._version(context)
        executable = str(before.evidence.get("executable", self.executable))
        resolved_executable = before.evidence.get(
            "resolved_executable", shutil.which(executable) or executable
        )
        command = (executable, "runtime", "update", "--all", "--yes")
        if not before.available:
            return UpdateResult(
                "unavailable", f"LM Studio runtime cannot be refreshed: {before.message}",
                before_version=before.version, source="lms runtime update",
                commands=(command,), evidence={
                    "executable": executable,
                    "resolved_executable": resolved_executable,
                },
            )
        result = self._run(command, context)
        if result.timed_out:
            return UpdateResult(
                "timed-out", "lms runtime update timed out", before_version=before.version,
                source="lms runtime update", commands=(command,),
                evidence={
                    "executable": executable,
                    "resolved_executable": resolved_executable,
                },
            )
        if result.returncode != 0:
            return UpdateResult(
                "failed", "lms runtime update failed", before_version=before.version,
                source="lms runtime update", commands=(command,),
                evidence={
                    "executable": executable,
                    "resolved_executable": resolved_executable,
                    "returncode": result.returncode,
                },
            )
        after = self._version(context)
        if not after.available:
            return UpdateResult(
                "failed", f"LM Studio CLI became unavailable after update: {after.message}",
                before_version=before.version, source="lms runtime update",
                commands=(command,), evidence={
                    "executable": executable,
                    "resolved_executable": resolved_executable,
                },
            )
        return UpdateResult(
            "updated" if before.version != after.version else "current",
            "LM Studio runtime refresh completed; CLI identity verified",
            before_version=before.version, after_version=after.version,
            source="lms runtime update", commands=(command,),
            warnings=("LM Studio CLI exposes a runtime update operation but not a desktop-app update operation",),
            evidence={
                "executable": executable,
                "resolved_executable": resolved_executable,
                "runtime_refresh": "completed",
                "runtime_version_provenance": "lms runtime update command; runtime version not separately exposed",
            },
        )

    def discover_models(self, context: ProbeContext | None = None) -> tuple[ModelOffer, ...]:
        context = context or ProbeContext()
        executable = str(context.metadata.get("provider_executable", self.executable))
        result = self._run((executable, "ls", "--llm", "--json"), context)
        if result.timed_out or result.returncode != 0:
            return ()
        return _model_offers(_json_object(result.stdout))

    def prepare(
        self, model: str, context: ProbeContext | None = None
    ) -> ProviderPreparation:
        """Start/load only what this run needs and register compensating cleanup."""

        context = context or ProbeContext()
        executable = str(context.metadata.get("provider_executable", self.executable))
        if not model.strip():
            return ProviderPreparation(
                ProbeResult(
                    "failed", False, "LM Studio model selection is empty",
                    source="provider/lm-studio",
                ),
                lambda: CleanupResult(
                    "not-applicable", "No LM Studio state was changed",
                    source="provider/lm-studio",
                ),
            )

        status_command = (executable, "server", "status", "--json")
        start_command = (executable, "server", "start")
        stop_command = (executable, "server", "stop")
        load_command = (executable, "load", model, "--yes")
        ps_command = (executable, "ps", "--json")
        commands = [list(status_command)]
        server = self._run(status_command, context)
        status = _json_object(server.stdout)
        running = _server_running(status)
        started_by_us = False
        load_attempted = False
        loaded_by_us = False
        loaded_model_to_unload = model
        original_loaded_ids: tuple[str, ...] = ()
        cleanup_done = False
        cleanup_result: CleanupResult | None = None

        def current_loaded_ids() -> tuple[str, ...] | None:
            loaded = self._run(ps_command, context)
            if loaded.timed_out or loaded.returncode != 0:
                return None
            value = _json_object(loaded.stdout)
            if value is None:
                return None
            return _loaded_model_ids(value)

        def cleanup() -> CleanupResult:
            """Undo only state this preparation may have introduced."""

            nonlocal cleanup_done, cleanup_result
            if cleanup_done and cleanup_result is not None:
                return cleanup_result
            cleanup_done = True
            actions: list[list[str]] = []
            warnings: list[str] = []
            failures: list[str] = []

            # A failed load can still leave a model resident. Inspecting first
            # keeps cleanup safe and avoids unloading a pre-existing model.
            if load_attempted or loaded_by_us:
                current = current_loaded_ids()
                if current is None:
                    failures.append("could not verify loaded models before cleanup")
                else:
                    matching = next(
                        (item for item in current if _model_matches(model, item)), None
                    )
                    if matching is not None and (
                        loaded_by_us or load_attempted
                    ) and matching not in original_loaded_ids:
                        unload = (executable, "unload", matching)
                        actions.append(list(unload))
                        result = self._run(unload, context)
                        if result.timed_out or result.returncode != 0:
                            failures.append("LM Studio model unload failed")

            if started_by_us:
                actions.append(list(stop_command))
                result = self._run(stop_command, context)
                if result.timed_out or result.returncode != 0:
                    failures.append("LM Studio server stop failed")

            if failures:
                cleanup_result = CleanupResult(
                    "partial" if actions else "failed",
                    "; ".join(failures),
                    source="lms provider transaction",
                    commands=tuple(tuple(action) for action in actions),
                    warnings=tuple(warnings),
                    evidence={
                        "executable": executable,
                        "model": model,
                        "started_by_us": started_by_us,
                        "loaded_by_us": loaded_by_us,
                    },
                )
            else:
                cleanup_result = CleanupResult(
                    "complete" if actions else "not-applicable",
                    "LM Studio state restored" if actions else "No LM Studio state was changed",
                    source="lms provider transaction",
                    commands=tuple(tuple(action) for action in actions),
                    evidence={
                        "executable": executable,
                        "model": model,
                        "started_by_us": started_by_us,
                        "loaded_by_us": loaded_by_us,
                    },
                )
            return cleanup_result

        def preparation(
            readiness: ProbeResult,
        ) -> ProviderPreparation:
            return ProviderPreparation(readiness, cleanup)

        if server.timed_out:
            return preparation(ProbeResult(
                "timed-out", False, "LM Studio server status timed out",
                source="lms server status --json",
                evidence={"executable": executable, "model": model, "actions": commands},
            ))
        if server.returncode != 0 or running is None:
            return preparation(ProbeResult(
                "failed", False, "LM Studio server readiness is unknown",
                source="lms server status --json",
                evidence={"executable": executable, "model": model, "actions": commands},
            ))

        if running:
            loaded = current_loaded_ids()
            commands.append(list(ps_command))
            if loaded is None:
                return preparation(ProbeResult(
                    "failed", False, "lms ps --json failed while reading loaded models",
                    source="lms ps --json",
                    evidence={"executable": executable, "model": model, "actions": commands},
                ))
            original_loaded_ids = loaded
        else:
            start_result = self._run(start_command, context)
            commands.append(list(start_command))
            started_by_us = True
            if start_result.timed_out or start_result.returncode != 0:
                return preparation(ProbeResult(
                    "failed", False, "LM Studio server start failed",
                    source="lms server start",
                    evidence={
                        "executable": executable, "model": model,
                        "server_running_before": False, "actions": commands,
                    },
                ))
            verify = self._run(status_command, context)
            commands.append(list(status_command))
            verified_status = _json_object(verify.stdout)
            if (
                verify.timed_out
                or verify.returncode != 0
                or _server_running(verified_status) is not True
            ):
                return preparation(ProbeResult(
                    "not-ready", False, "LM Studio server did not become ready after start",
                    source="lms server status --json",
                    evidence={
                        "executable": executable, "model": model,
                        "server_running_before": False, "actions": commands,
                    },
                ))

        if any(_model_matches(model, item) for item in original_loaded_ids):
            return preparation(ProbeResult(
                "ready", True, "LM Studio server and selected model are ready",
                source="lms ps --json",
                evidence={
                    "executable": executable, "model": model,
                    "server_running": True,
                    "loaded_models": list(original_loaded_ids),
                    "actions": commands,
                    "provider_mutation": "none",
                },
            ))

        load_attempted = True
        load_result = self._run(load_command, context)
        commands.append(list(load_command[:-1]) + ["--yes"])
        if load_result.timed_out or load_result.returncode != 0:
            return preparation(ProbeResult(
                "failed", False, f"LM Studio could not load selected model {model!r}",
                source="lms load",
                evidence={
                    "executable": executable, "model": model,
                    "server_running": True, "actions": commands,
                },
            ))

        loaded_after = current_loaded_ids()
        commands.append(list(ps_command))
        if loaded_after is None:
            return preparation(ProbeResult(
                "failed", False, "lms ps --json failed while verifying model load",
                source="lms ps --json",
                evidence={"executable": executable, "model": model, "actions": commands},
            ))
        selected_loaded = next(
            (item for item in loaded_after if _model_matches(model, item)), None
        )
        if selected_loaded is None:
            return preparation(ProbeResult(
                "not-ready", False,
                f"selected model {model!r} was not present after LM Studio load",
                source="lms ps --json",
                evidence={
                    "executable": executable, "model": model,
                    "server_running": True, "loaded_models": list(loaded_after),
                    "actions": commands,
                },
            ))
        loaded_by_us = True
        # Keep the concrete identifier used by `ps` in cleanup evidence and
        # use it for the unload command when it differs from the model key.
        return preparation(ProbeResult(
            "ready", True, "LM Studio server and selected model are ready",
            source="lms ps --json",
            evidence={
                "executable": executable, "model": model,
                "server_running": True, "loaded_models": list(loaded_after),
                "actions": commands,
                "provider_mutation": (
                    "server-start-and-model-load" if started_by_us else "model-load"
                ),
                "cleanup_model": selected_loaded,
            },
        ))

    def option_schema(self) -> dict[str, object]:
        return {"endpoint": {"default": "http://127.0.0.1:1234/v1"}}

    def connection_settings(self, context: ProbeContext | None = None) -> dict[str, object]:
        context = context or ProbeContext()
        endpoint = context.metadata.get("provider_endpoint", "http://127.0.0.1:1234/v1")
        if not isinstance(endpoint, str) or not endpoint.strip():
            endpoint = "http://127.0.0.1:1234/v1"
        return {
            "native_name": "lmstudio",
            "base_url": endpoint,
            "api": "openai-completions",
            "credential_mode": "local-placeholder",
        }

    def cost_capabilities(self) -> CostCapabilities:
        return CostCapabilities(
            billing_modes=("local",),
            evidence_statuses=("unavailable",),
            usage_sources=("provider-local",),
        )


__all__ = ["LMStudioProviderAdapter"]
