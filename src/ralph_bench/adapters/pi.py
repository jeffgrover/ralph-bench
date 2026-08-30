"""Pi harness boundary, including the native Pi-wiggum extension surface."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable

from .contracts import (
    AdapterDescriptor,
    ConnectionProbe,
    HarnessExecutionContext,
    InvocationPlan,
    ProbeContext,
    ProbeResult,
    ProcessResult,
    UpdateResult,
)


_VERSION_PATTERN = re.compile(r"^(?P<version>[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)$")
_PACKAGE_PATTERN = re.compile(r"^(?:npm|git|https?)[:@/][^\s]+$")


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


def _package_ids(output: str) -> tuple[str, ...]:
    """Keep only bounded package-like identities from ``pi list`` output."""

    values: list[str] = []
    for line in output.splitlines():
        value = line.strip()
        if value and _PACKAGE_PATTERN.fullmatch(value) and value not in values:
            values.append(value)
        if len(values) >= 64:
            break
    return tuple(values)


def _extension_inventory(
    output: str, context: ProbeContext
) -> tuple[tuple[str, ...], dict[str, str]]:
    """Read bounded, non-secret package manifests for npm extensions."""

    identities = _package_ids(output)
    root_value = context.metadata.get(
        "pi_extension_root", str(Path.home() / ".pi" / "agent" / "npm" / "node_modules")
    )
    root = Path(root_value) if isinstance(root_value, str) else None
    versions: dict[str, str] = {}
    if root is None:
        return identities, versions
    for identity in identities:
        if not identity.startswith("npm:"):
            continue
        package = identity.removeprefix("npm:")
        parts = package.split("/")
        if not parts or any(part in {"", ".", ".."} for part in parts):
            continue
        manifest = root.joinpath(*parts, "package.json")
        try:
            if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 64 * 1024:
                continue
            value = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and isinstance(value.get("version"), str) and value["version"].strip():
            versions[identity] = value["version"].strip()
    return identities, versions


def _update_failure_message(command: tuple[str, ...], result: ProcessResult) -> str:
    """Classify known package-manager failures without preserving raw output."""

    text = (result.stdout + "\n" + result.stderr).casefold()
    if "global npm install" in text and "not writable" in text:
        return (
            f"{' '.join(command)} failed because the global npm Pi installation "
            "is not writable; update that installation through its package manager"
        )
    return f"{' '.join(command)} failed"


class PiHarnessAdapter:
    descriptor = AdapterDescriptor(
        "harness/pi",
        "harness",
        "Pi",
        capabilities=("jsonl-events", "native-loop", "explicit-model", "local-provider"),
        detection="executable",
        limitations=(
            "Pi-wiggum is a native extension workflow; its first live proving run awaits model selection",
        ),
    )

    def __init__(
        self,
        executable: str = "pi",
        process_runner: Callable[[tuple[str, ...], float], ProcessResult] | None = None,
        extension_root: str | Path | None = None,
        attempt_executor_factory: Callable[..., object] | None = None,
    ) -> None:
        self.executable = executable
        self._runner = process_runner or _default_runner
        self.extension_root = Path(extension_root) if extension_root else (
            Path.home() / ".pi" / "agent" / "npm" / "node_modules" / "pi-wiggum"
        )
        self._attempt_executor_factory = attempt_executor_factory

    def _run(self, argv: tuple[str, ...], context: ProbeContext) -> ProcessResult:
        return (context.process_runner or self._runner)(argv, context.timeout_seconds)

    def detect(self, context: ProbeContext | None = None) -> ProbeResult:
        context = context or ProbeContext()
        executable = context.executable or self.executable
        if context.process_runner is None and shutil.which(executable) is None:
            return ProbeResult(
                "unavailable", False, f"{executable!r} was not found", source="pi --version"
            )
        result = self._run((executable, "--version"), context)
        if result.timed_out:
            return ProbeResult("timed-out", False, "pi --version timed out", source="pi --version")
        if result.returncode != 0:
            return ProbeResult("failed", False, "pi --version failed", source="pi --version")
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
                "failed", False, "pi --version returned an unrecognized version format",
                source="pi --version",
            )
        return ProbeResult(
            "ok",
            True,
            "Pi detected",
            version=version,
            source="pi --version",
            evidence={
                "executable": executable,
                "resolved_executable": shutil.which(executable) or executable,
                "native_extension": "pi-wiggum",
            },
        )

    def ensure_current(self, context: ProbeContext | None = None) -> UpdateResult:
        """Refresh Pi and its installed extension graph, then verify Pi."""

        context = context or ProbeContext()
        executable = context.executable or self.executable
        before = self.detect(context)
        resolved_executable = before.evidence.get(
            "resolved_executable", shutil.which(executable) or executable
        )
        commands = (
            (executable, "update"),
            (executable, "update", "--extensions"),
        )
        if not before.available:
            return UpdateResult(
                "unavailable",
                f"Pi cannot be refreshed: {before.message}",
                before_version=before.version,
                source="pi update",
                commands=commands,
                evidence={
                    "executable": executable,
                    "resolved_executable": resolved_executable,
                },
            )
        before_list_command = (executable, "list", "--no-approve")
        before_list = self._run(before_list_command, context)
        before_packages, before_versions = _extension_inventory(before_list.stdout, context)
        failures: list[tuple[tuple[str, ...], ProcessResult]] = []
        returncodes: dict[str, int] = {}
        timed_out: tuple[str, ...] | None = None
        for command in commands:
            result = self._run(command, context)
            returncodes[" ".join(command)] = result.returncode
            if result.timed_out:
                timed_out = command
                break
            if result.returncode != 0:
                failures.append((command, result))
        if timed_out is not None:
            return UpdateResult(
                "timed-out",
                f"{' '.join(timed_out)} timed out",
                before_version=before.version,
                source="pi update",
                commands=commands,
                evidence={
                    "executable": executable,
                    "resolved_executable": resolved_executable,
                    "returncodes": returncodes,
                },
            )
        after = self.detect(context)
        if not after.available:
            return UpdateResult(
                "failed",
                f"Pi became unavailable after update: {after.message}",
                before_version=before.version,
                source="pi update",
                commands=commands,
                evidence={
                    "executable": executable,
                    "resolved_executable": resolved_executable,
                },
            )
        after_list_command = (executable, "list", "--no-approve")
        after_list = self._run(after_list_command, context)
        package_ids, after_versions = _extension_inventory(after_list.stdout, context)
        evidence: dict[str, object] = {
            "executable": executable,
            "resolved_executable": resolved_executable,
            "native_extension": "pi-wiggum",
            "extension_identities_before": list(before_packages),
            "extension_identities_after": list(package_ids),
            "extension_versions_before": before_versions,
            "extension_versions_after": after_versions,
        }
        warnings = ()
        if not package_ids:
            warnings = ("Pi did not expose installed extension identities in `pi list` output",)
        if failures:
            failed, failed_result = failures[0]
            return UpdateResult(
                "failed",
                _update_failure_message(failed, failed_result),
                before_version=before.version,
                after_version=after.version,
                source="pi update",
                commands=(before_list_command,) + commands + (after_list_command,),
                warnings=warnings,
                evidence={
                    **evidence,
                    "returncodes": returncodes,
                    "failed_commands": [list(command) for command, _result in failures],
                },
            )
        return UpdateResult(
            "updated" if before.version != after.version else "current",
            "Pi and installed extensions refreshed; current executable verified",
            before_version=before.version,
            after_version=after.version,
            source="pi update",
            commands=(before_list_command,) + commands + (after_list_command,),
            warnings=warnings,
            evidence=evidence,
        )

    def connection_requirements(self) -> tuple[str, ...]:
        return ("local-provider",)

    def credential_reference(self) -> Path | None:
        return None

    def environment_overrides(
        self, scoped_home: Path, credential_reference: Path | None = None
    ) -> dict[str, str]:
        del credential_reference
        return {"PI_CODING_AGENT_DIR": str(scoped_home / ".pi" / "agent")}

    def connection_probe(self, context: ProbeContext | None = None) -> ConnectionProbe:
        return ConnectionProbe(
            "ok",
            True,
            self.connection_requirements(),
            ("local-provider",),
            None,
            "Pi can use a provider-owned local runtime",
            "pi descriptor",
        )

    def option_schema(self) -> dict[str, object]:
        return {
            "reasoning_effort": {"values": ("none", "low", "medium", "high", "xhigh", "max")},
            "loop": {"values": ("native",)},
        }

    def plan(
        self,
        model: str,
        reasoning_effort: str = "medium",
        sandbox: str = "workspace-write",
        working_directory: str | None = None,
        executable: str | None = None,
    ) -> InvocationPlan:
        if reasoning_effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError(f"unsupported Pi thinking level: {reasoning_effort}")
        if sandbox not in {"read-only", "workspace-write"}:
            raise ValueError(f"unsupported Pi sandbox: {sandbox}")
        argv_parts = [
            executable or self.executable,
            "--mode", "json",
            "--print",
            "--no-session",
            "--approve",
            "--provider", "lmstudio",
            "--model", model,
            "--thinking", "off" if reasoning_effort == "none" else reasoning_effort,
        ]
        resources = (
            self.extension_root / "extensions" / "plan-mode-guard.ts",
            self.extension_root / "extensions" / "stop-guard.ts",
            self.extension_root.parent / "pi-subagents" / "index.ts",
        )
        warnings: list[str] = []
        for resource in resources:
            if resource.is_file():
                argv_parts.extend(("--extension", str(resource)))
            else:
                warnings.append(f"Pi native resource is missing: {resource.name}")
        prompt_template = self.extension_root / "prompts" / "wiggum.md"
        if prompt_template.is_file():
            argv_parts.extend(("--prompt-template", str(prompt_template)))
        else:
            warnings.append("Pi-wiggum prompt template is missing")
        return InvocationPlan(
            argv=tuple(argv_parts),
            model=model,
            sandbox=sandbox,
            working_directory=working_directory,
            stdin_mode="prompt",
            prompt_argument="-",
            evidence_prefix="pi-wiggum",
            warnings=tuple(warnings),
        )

    def create_attempt_executor(self, context: HarnessExecutionContext):
        """Create the native Pi-wiggum executor behind the harness boundary."""

        factory = self._attempt_executor_factory
        if factory is not None:
            return factory(context)
        from .pi_execution import PiAttemptExecutor

        return PiAttemptExecutor(
            context,
            provider_settings=context.metadata.get(
                "provider_settings",
                {"native_name": "lmstudio", "base_url": "http://127.0.0.1:1234/v1"},
            ),
        )


__all__ = ["PiHarnessAdapter"]
