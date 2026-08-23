"""Honest P0 staged-workspace isolation and environment construction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
import json
import os
from pathlib import Path
import re
import shutil
import stat


ISOLATION_SCHEMA_VERSION = "isolation/v1"
STAGED_IMPLEMENTATION = "staged-workspace/v1"


class IsolationError(RuntimeError):
    """Raised when a staged workspace cannot be constructed safely."""


class IsolationLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"


class CanaryStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"
    UNKNOWN = "unknown"


class NetworkCapability(StrEnum):
    RESTRICTED = "restricted"
    UNRESTRICTED = "unrestricted"
    UNKNOWN = "unknown"


_SECRET_ENV_MARKERS = (
    "API_KEY",
    "AUTH_TOKEN",
    "BEARER",
    "COOKIE",
    "CREDENTIAL",
    "PASSWORD",
    "PRIVATE_KEY",
    "SECRET",
    "SESSION_TOKEN",
    "TOKEN",
)

_CREDENTIAL_PATH_KEYS = frozenset(
    {
        "AWS_SHARED_CREDENTIALS_FILE",
        "AZURE_CONFIG_DIR",
        "CODEX_HOME",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "KUBECONFIG",
        "NETRC",
        "SSH_AUTH_SOCK",
    }
)

DEFAULT_ENV_ALLOWLIST = frozenset(
    {
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "NO_COLOR",
        "PATH",
        "SYSTEMROOT",
        "TERM",
        "TMP",
        "TEMP",
        "TZ",
    }
)


def _is_secret_key(key: str) -> bool:
    upper = key.upper()
    return upper in _CREDENTIAL_PATH_KEYS or any(
        marker in upper for marker in _SECRET_ENV_MARKERS
    )


def build_process_environment(
    source: Mapping[str, str],
    *,
    scoped_home: Path,
    allowlist: Sequence[str] = tuple(DEFAULT_ENV_ALLOWLIST),
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build an allowlisted agent environment without credential values."""

    allowed = set(allowlist)
    if any(_is_secret_key(key) for key in allowed):
        raise IsolationError("environment allowlist contains a secret-bearing key")
    result = {key: source[key] for key in sorted(allowed) if key in source}
    result.update(
        {
            "HOME": str(scoped_home),
            "XDG_CACHE_HOME": str(scoped_home / ".cache"),
            "XDG_CONFIG_HOME": str(scoped_home / ".config"),
            "XDG_DATA_HOME": str(scoped_home / ".local/share"),
            "XDG_STATE_HOME": str(scoped_home / ".local/state"),
        }
    )
    for key, value in sorted((overrides or {}).items()):
        if _is_secret_key(key):
            raise IsolationError(
                f"credential-like environment override is prohibited: {key}"
            )
        result[key] = value
    return result


def secret_environment_keys(environment: Mapping[str, str]) -> tuple[str, ...]:
    """Return key names only; values are deliberately never returned."""

    return tuple(sorted(key for key in environment if _is_secret_key(key)))


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_public_tree(source: Path) -> None:
    if not source.is_dir() or source.is_symlink():
        raise IsolationError(f"public input must be a real directory: {source}")
    for current_root, directory_names, file_names in os.walk(source, followlinks=False):
        current = Path(current_root)
        for name in directory_names + file_names:
            path = current / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise IsolationError(f"public input contains a symlink: {path}")
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise IsolationError(f"public input contains a special file: {path}")


def _copy_public_tree(source: Path, destination: Path) -> None:
    _validate_public_tree(source)
    shutil.copytree(source, destination, symlinks=False)


def _make_read_only(root: Path) -> None:
    for current_root, directory_names, file_names in os.walk(root):
        current = Path(current_root)
        for name in file_names:
            (current / name).chmod(0o444)
        for name in directory_names:
            (current / name).chmod(0o555)
    root.chmod(0o555)


def _make_writable(root: Path) -> None:
    if not root.exists():
        return
    for current_root, directory_names, file_names in os.walk(root):
        current = Path(current_root)
        current.chmod(0o700)
        for name in directory_names:
            (current / name).chmod(0o700)
        for name in file_names:
            (current / name).chmod(0o600)


@dataclass(frozen=True, slots=True)
class StagedWorkspace:
    run_id: str
    base_root: Path
    run_root: Path
    public_challenge: Path
    workspace: Path
    public_tools: Path
    scoped_home: Path
    conductor_root: Path

    @classmethod
    def create(
        cls,
        *,
        base_root: Path,
        run_id: str,
        public_challenge_source: Path,
        public_tools_source: Path | None = None,
        forbidden_roots: Sequence[Path] = (),
    ) -> "StagedWorkspace":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
            raise IsolationError("run ID contains unsupported path characters")

        resolved_base = base_root.resolve()
        asset_roots = [public_challenge_source]
        if public_tools_source is not None:
            asset_roots.append(public_tools_source)
        for forbidden in (*forbidden_roots, *asset_roots):
            resolved_forbidden = forbidden.resolve()
            if _path_is_within(resolved_base, resolved_forbidden) or _path_is_within(
                resolved_forbidden, resolved_base
            ):
                raise IsolationError("staging and forbidden asset roots overlap")

        base_root.mkdir(parents=True, exist_ok=True)
        run_root = base_root / f"rb-agent-{run_id}"
        conductor_root = base_root / f"rb-conductor-{run_id}"
        if run_root.exists() or conductor_root.exists():
            raise IsolationError("staged run roots already exist")

        try:
            run_root.mkdir(mode=0o700)
            conductor_root.mkdir(mode=0o700)
            marker = {"implementation": STAGED_IMPLEMENTATION, "run_id": run_id}
            (run_root / ".rb-staged-workspace").write_text(
                json.dumps(marker, sort_keys=True), encoding="utf-8"
            )
            (conductor_root / ".rb-conductor-root").write_text(
                json.dumps(marker, sort_keys=True), encoding="utf-8"
            )
            public_challenge = run_root / "public-challenge"
            public_tools = run_root / "public-tools"
            workspace = run_root / "workspace"
            scoped_home = run_root / "scoped-home"
            _copy_public_tree(public_challenge_source, public_challenge)
            if public_tools_source is None:
                public_tools.mkdir(mode=0o755)
            else:
                _copy_public_tree(public_tools_source, public_tools)
            workspace.mkdir(mode=0o700)
            scoped_home.mkdir(mode=0o700)
            _make_read_only(public_challenge)
            _make_read_only(public_tools)
        except Exception:
            _make_writable(run_root)
            shutil.rmtree(run_root, ignore_errors=True)
            shutil.rmtree(conductor_root, ignore_errors=True)
            raise

        return cls(
            run_id=run_id,
            base_root=base_root,
            run_root=run_root,
            public_challenge=public_challenge,
            workspace=workspace,
            public_tools=public_tools,
            scoped_home=scoped_home,
            conductor_root=conductor_root,
        )

    def cleanup(self) -> None:
        """Remove only roots carrying the expected ownership markers."""

        targets = (
            (self.run_root, ".rb-staged-workspace"),
            (self.conductor_root, ".rb-conductor-root"),
        )
        for target, marker_name in targets:
            if not target.exists():
                continue
            if target.is_symlink() or not target.is_dir():
                raise IsolationError("refusing cleanup of a non-directory run root")
            expected_parent = self.base_root.resolve()
            if target.resolve().parent != expected_parent:
                raise IsolationError("refusing cleanup outside the staging parent")
            marker_path = target / marker_name
            try:
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise IsolationError("refusing cleanup without a valid ownership marker") from exc
            if marker.get("run_id") != self.run_id or marker.get(
                "implementation"
            ) != STAGED_IMPLEMENTATION:
                raise IsolationError("refusing cleanup with a mismatched ownership marker")
            _make_writable(target)
            shutil.rmtree(target)


@dataclass(frozen=True, slots=True)
class IsolationReport:
    level: IsolationLevel
    implementation: str
    publication_class: str
    staged_assets_only: bool
    environment_allowlisted: bool
    filesystem_enforced: bool
    credential_canary: CanaryStatus
    agent_network: NetworkCapability
    environment_keys: tuple[str, ...]
    limitations: tuple[str, ...]
    schema_version: str = ISOLATION_SCHEMA_VERSION

    def to_metadata(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "level": self.level.value,
            "implementation": self.implementation,
            "publication_class": self.publication_class,
            "staged_assets_only": self.staged_assets_only,
            "environment_allowlisted": self.environment_allowlisted,
            "filesystem_enforced": self.filesystem_enforced,
            "credential_canary": self.credential_canary.value,
            "agent_network": self.agent_network.value,
            "environment_keys": list(self.environment_keys),
            "limitations": list(self.limitations),
        }


def build_isolation_report(
    *,
    environment: Mapping[str, str],
    credential_canary: CanaryStatus,
    agent_network: NetworkCapability = NetworkCapability.UNKNOWN,
    requires_credentials: bool = True,
) -> IsolationReport:
    secret_keys = secret_environment_keys(environment)
    allowlisted = not secret_keys
    limitations = [
        "benchmark-owned filesystem confidentiality is not independently enforced",
        "provider and agent-tool network channels are not independently enforced",
    ]
    if secret_keys:
        limitations.append("credential-like environment keys reached the agent process")
    if requires_credentials and credential_canary is not CanaryStatus.PASSED:
        limitations.append("credential isolation was not demonstrated")
    return IsolationReport(
        level=IsolationLevel.L0,
        implementation=STAGED_IMPLEMENTATION,
        publication_class="unsealed",
        staged_assets_only=True,
        environment_allowlisted=allowlisted,
        filesystem_enforced=False,
        credential_canary=credential_canary,
        agent_network=agent_network,
        environment_keys=tuple(sorted(environment)),
        limitations=tuple(limitations),
    )
