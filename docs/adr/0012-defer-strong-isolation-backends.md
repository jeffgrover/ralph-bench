# ADR 0012: Defer strong isolation backends

- Status: accepted
- Date: 2026-08-23

## Context

The first live implementation used Linux Bubblewrap to separate the Codex
parent, candidate workspace, public challenge, credentials, and provider/tool
network channels. That approach made the P0 path Linux-specific while Ralph
Bench is intended to run on Linux, macOS, and Windows hardware. Selecting
Bubblewrap early would also have made one platform tool an accidental core
abstraction before comparing native sandboxes, WSL, containers, and VMs.

## Decision

P0 uses portable, explicitly best-effort protection:

- A fresh staged candidate workspace.
- Only public challenge material is intentionally delivered.
- A sanitized child environment with the credential access required by the
  Codex parent.
- Codex's native `workspace-write` mode.
- Conductor-owned timing, judging, redaction, and bundle assembly outside the
  candidate tree.
- Provenance fixed at `L0` / `unsealed`.

P0 does not claim that credentials, judge material, the repository, prior
results, or unrelated host files are unreadable to a determined agent. L0
results may be shared in a clearly labeled experimental view but are excluded
from official rankings.

Selection and implementation of strong L1/L2 isolation is deferred to a
separate cross-platform milestone. Candidate tools include Bubblewrap,
Seatbelt/App Sandbox, WSL/Windows facilities, containers, and virtual machines;
none is preferred by this ADR.

## Consequences

- The P0 conductor remains usable while platform portability is developed.
- Isolation metadata is an honest capability report rather than a sandbox
  brand name.
- Credential canaries and network-channel separation are not P0 gates.
- Strong-isolation results must introduce a versioned backend and demonstrate
  their claims with platform-specific canaries before receiving L1/L2 labels.
