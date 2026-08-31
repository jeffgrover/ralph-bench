"""Codex CLI harness boundary.

Detection and auth are read-only.  Invocation planning is data-only; the
conductor that eventually executes the plan is outside this P0-A slice.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
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


_VERSION_PATTERN = re.compile(
    r"^codex-cli[ \t]+(?P<version>[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)$"
)


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


class CodexHarnessAdapter:
    descriptor = AdapterDescriptor(
        "harness/codex-cli",
        "harness",
        "Codex CLI",
        capabilities=("jsonl-events", "ephemeral", "explicit-model", "sandbox"),
        detection="executable",
        limitations=(
            "P0-A uses portable L0 staged-workspace protection; strong isolation is deferred",
        ),
    )

    def __init__(
        self,
        executable: str = "codex",
        process_runner: Callable[[tuple[str, ...], float], ProcessResult] | None = None,
        attempt_executor_factory: Callable[[HarnessExecutionContext], object] | None = None,
        credential_reference_factory: Callable[[], Path | None] | None = None,
    ) -> None:
        self.executable = executable
        self._runner = process_runner or _default_runner
        self._attempt_executor_factory = attempt_executor_factory
        self._credential_reference_factory = credential_reference_factory

    def _run(self, argv: tuple[str, ...], context: ProbeContext) -> ProcessResult:
        return (context.process_runner or self._runner)(argv, context.timeout_seconds)

    def detect(self, context: ProbeContext | None = None) -> ProbeResult:
        context = context or ProbeContext()
        executable = context.executable or self.executable
        if context.process_runner is None and shutil.which(executable) is None:
            return ProbeResult(
                "unavailable", False, f"{executable!r} was not found", source="codex --version"
            )
        result = self._run((executable, "--version"), context)
        if result.timed_out:
            return ProbeResult("timed-out", False, "codex --version timed out", source="codex --version")
        if result.returncode != 0:
            return ProbeResult(
                "failed", False, "codex --version failed", source="codex --version"
            )
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
                "failed",
                False,
                "codex --version returned an unrecognized version format",
                source="codex --version",
            )
        return ProbeResult(
            "ok", True, "Codex CLI detected", version=version,
            source="codex --version",
            warnings=(
                "invocation compatibility is confirmed during current-toolchain preflight",
            ),
            evidence={
                "executable": executable,
                "resolved_executable": shutil.which(executable) or executable,
            },
        )

    def ensure_current(self, context: ProbeContext | None = None) -> UpdateResult:
        """Refresh Codex before a run, then verify the installed executable."""

        context = context or ProbeContext()
        executable = context.executable or self.executable
        before = self.detect(context)
        resolved_executable = before.evidence.get(
            "resolved_executable", shutil.which(executable) or executable
        )
        command = (executable, "update")
        if not before.available:
            return UpdateResult(
                "unavailable",
                f"Codex cannot be refreshed: {before.message}",
                before_version=before.version,
                source="codex update",
                commands=(command,),
                evidence={"executable": executable, "resolved_executable": resolved_executable},
            )
        result = self._run(command, context)
        if result.timed_out:
            return UpdateResult(
                "timed-out",
                "codex update timed out",
                before_version=before.version,
                source="codex update",
                commands=(command,),
                evidence={"executable": executable, "resolved_executable": resolved_executable},
            )
        if result.returncode != 0:
            return UpdateResult(
                "failed",
                "codex update failed",
                before_version=before.version,
                source="codex update",
                commands=(command,),
                evidence={
                    "executable": executable,
                    "resolved_executable": resolved_executable,
                    "returncode": result.returncode,
                },
            )
        after = self.detect(context)
        if not after.available:
            return UpdateResult(
                "failed",
                f"Codex became unavailable after update: {after.message}",
                before_version=before.version,
                source="codex update",
                commands=(command,),
                evidence={"executable": executable, "resolved_executable": resolved_executable},
            )
        status = "updated" if before.version != after.version else "current"
        return UpdateResult(
            status,
            "Codex update completed; current executable verified",
            before_version=before.version,
            after_version=after.version,
            source="codex update",
            commands=(command,),
            evidence={
                "executable": executable,
                "resolved_executable": resolved_executable,
                "returncode": result.returncode,
            },
        )

    def auth_probe(self, context: ProbeContext | None = None) -> ProbeResult:
        context = context or ProbeContext()
        executable = context.executable or self.executable
        result = self._run((executable, "login", "status"), context)
        lowered = (result.stdout + "\n" + result.stderr).lower()
        if result.timed_out:
            return ProbeResult("timed-out", False, "codex login status timed out", source="codex login status")
        negative = ("not logged in", "not authenticated", "logged out", "unauthenticated")
        if result.returncode == 0 and not any(item in lowered for item in negative) and (
            "logged in" in lowered or "authenticated" in lowered
        ):
            return ProbeResult(
                "ok", True, "Codex reports an authenticated session",
                source="codex login status", evidence={"credential_available": True},
            )
        return ProbeResult(
            "unauthorized", False, "Codex is not authenticated; run `codex login`",
            source="codex login status", evidence={"credential_available": False},
        )

    def connection_requirements(self) -> tuple[str, ...]:
        return ("chatgpt-subscription",)

    def credential_reference(self) -> Path | None:
        if self._credential_reference_factory is not None:
            return self._credential_reference_factory()
        codex_home_value = os.environ.get("CODEX_HOME")
        codex_home = Path(codex_home_value) if codex_home_value else Path.home() / ".codex"
        auth = codex_home / "auth.json"
        if not auth.is_file() or auth.is_symlink():
            return None
        return auth.resolve()

    def environment_overrides(
        self, scoped_home: Path, credential_reference: Path | None = None
    ) -> dict[str, str]:
        del scoped_home
        if credential_reference is None:
            return {}
        return {"CODEX_HOME": str(credential_reference.parent)}

    def connection_probe(self, context: ProbeContext | None = None) -> ConnectionProbe:
        auth = self.auth_probe(context)
        return ConnectionProbe(
            auth.status,
            auth.available,
            self.connection_requirements(),
            ("chatgpt-subscription",),
            auth.evidence.get("credential_available"),
            auth.message,
            auth.source,
            auth.warnings,
        )

    def option_schema(self) -> dict[str, object]:
        return {
            "reasoning_effort": {"values": ("none", "low", "medium", "high", "xhigh", "max")},
            "loop": {"values": ("controlled", "native")},
        }

    def plan(
        self,
        model: str,
        reasoning_effort: str = "medium",
        sandbox: str = "workspace-write",
        working_directory: str | None = None,
        executable: str | None = None,
        loop: str = "controlled",
    ) -> InvocationPlan:
        if loop not in {"controlled", "native"}:
            raise ValueError(f"unsupported Codex loop: {loop}")
        efforts = {"none", "low", "medium", "high", "xhigh", "max"}
        if reasoning_effort not in efforts:
            raise ValueError(f"unsupported Codex reasoning effort: {reasoning_effort}")
        if sandbox not in {"read-only", "workspace-write"}:
            raise ValueError(f"unsupported Codex sandbox: {sandbox}")
        # The current-toolchain preflight verifies the installed CLI before
        # this plan is used. The -c value is TOML, including its quoted
        # string, rather than a shell fragment.
        argv = (
            executable or self.executable,
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--json",
            "--ephemeral",
            "--model",
            model,
            "--sandbox",
            sandbox,
            "--skip-git-repo-check",
            "-c",
            f'model_reasoning_effort="{reasoning_effort}"',
        )
        if working_directory is not None:
            argv += ("-C", working_directory)
        argv += ("-",)
        return InvocationPlan(
            argv=argv,
            model=model,
            sandbox=sandbox,
            working_directory=working_directory,
            stdin_mode="prompt",
            prompt_argument="-",
        )

    def create_attempt_executor(self, context: HarnessExecutionContext):
        """Create the Codex-specific executor behind the harness boundary."""

        factory = self._attempt_executor_factory
        if factory is not None:
            return factory(context)
        from .codex_execution import CodexAttemptExecutor

        return CodexAttemptExecutor(
            plan=context.plan,
            workspace=context.workspace,
            evidence_root=context.evidence_root,
            prompt=context.prompt,
            environment=context.environment,
            timeout_seconds=context.timeout_seconds,
            runner=context.runner,
            secret_values=context.secret_values,
        )
