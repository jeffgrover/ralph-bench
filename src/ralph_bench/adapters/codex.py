"""Codex CLI harness boundary.

Detection and auth are read-only.  Invocation planning is data-only; the
conductor that eventually executes the plan is outside this P0-A slice.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Callable

from .contracts import (
    AdapterDescriptor,
    ConnectionProbe,
    InvocationPlan,
    ProbeContext,
    ProbeResult,
    ProcessResult,
)


SUPPORTED_CODEX_VERSIONS = frozenset({"0.149.0"})
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
    ) -> None:
        self.executable = executable
        self._runner = process_runner or _default_runner

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
        if version not in SUPPORTED_CODEX_VERSIONS:
            supported = ", ".join(sorted(SUPPORTED_CODEX_VERSIONS))
            return ProbeResult(
                "unsupported",
                False,
                f"Codex CLI {version} is not supported by this adapter; tested: {supported}",
                version=version,
                source="codex --version",
                evidence={"executable": executable},
            )
        return ProbeResult(
            "ok", True, "Codex CLI detected", version=version,
            source="codex --version", evidence={"executable": executable},
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
    ) -> InvocationPlan:
        efforts = {"none", "low", "medium", "high", "xhigh", "max"}
        if reasoning_effort not in efforts:
            raise ValueError(f"unsupported Codex reasoning effort: {reasoning_effort}")
        if sandbox not in {"read-only", "workspace-write"}:
            raise ValueError(f"unsupported Codex sandbox: {sandbox}")
        # Every option here is supported by Codex CLI 0.149.0.  The -c value is
        # TOML, including its quoted string, rather than a shell fragment.
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
