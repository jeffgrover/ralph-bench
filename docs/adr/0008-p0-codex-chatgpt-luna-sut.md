# ADR 0008: Use Codex CLI, ChatGPT Access, and Luna for the P0 Live SUT

**Status:** Accepted
**Date:** 2026-08-23

## Context

P0 needs one real system-under-test composition to prove that guided authoring,
adapter resolution, isolated execution, event capture, evaluation, immutable
bundling, and reporting work end to end. Supporting multiple real harnesses,
local runtimes, cloud billing paths, and model families simultaneously would
increase integration scope before the polymorphic contracts are stable.

Current official OpenAI documentation establishes that:

- Codex CLI supports signing in with ChatGPT for subscription access and
  exposes `codex login status` for read-only authentication preflight.
- `gpt-5.6-luna` is available in Codex CLI and can be selected explicitly.
- `codex exec` supports non-interactive execution, ephemeral sessions, explicit
  sandboxing, ignored user config, and machine-readable JSONL events with usage.

References:

- [Codex authentication](https://learn.chatgpt.com/docs/auth)
- [Codex models](https://learn.chatgpt.com/docs/models)
- [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
- [ChatGPT and Codex pricing](https://learn.chatgpt.com/docs/pricing)
- [GPT-5.6 Luna API pricing](https://developers.openai.com/api/docs/models/gpt-5.6-luna)

### Planning-host observation

On 2026-08-23, the intended development host reports `codex-cli 0.149.0` and
`Logged in using ChatGPT`. Its `codex exec --help` exposes explicit model,
JSONL, ephemeral, user-config isolation, sandbox, working-directory, and config
override options. This is feasibility evidence, not a permanent version pin or
proof that the account can invoke Luna; implementation pins the tested version
and performs a live entitlement preflight.

## Decision

The only required live P0 SUT is:

```text
Harness:  Codex CLI
Provider: ChatGPT-managed OpenAI access
Model:    gpt-5.6-luna
Track:    cloud-subscription
```

The user-facing provider choice is shown as **ChatGPT (subscription)**. The
canonical provider adapter ID may be `openai-chatgpt`; it represents the
authentication, entitlement, service, and billing path, not a claim that
ChatGPT is a generic model API endpoint.

Reasoning effort remains an explicit experiment parameter. This decision does
not silently fix it to the CLI default or to a benchmark-wide value.

The Codex harness adapter uses a pinned and recorded CLI version and an
explicit invocation derived from the resolved plan. The proposed shape is
`codex exec --json --ephemeral` with an explicit model, sandbox, and isolated or
ignored user configuration. Exact supported flags are verified against the
pinned version during implementation.

Authentication remains operator-managed. `rb` may inspect `codex login status`
and explain how to run `codex login`, but it does not copy, print, archive, or
silently replace ChatGPT credentials.

Because Codex exposes this authentication status through its own executable,
the Codex harness adapter performs the command and returns a canonical
connection/authentication offer. The ChatGPT provider adapter validates and
interprets that offer as provider, entitlement, billing, and provenance data.
The provider adapter does not secretly invoke a concrete harness, and the
harness adapter does not redefine provider semantics.

The adapter must preserve raw stdout JSONL and stderr, normalize events and
usage, and record the requested and effective model/authentication path.

Other real harnesses, providers, and models—including OpenCode, LM Studio,
API-key-metered OpenAI, and local models—are TBD and post-P0 unless this ADR is
amended. Fake adapters still exercise the full polymorphic composition matrix
and provider lifecycle contracts during P0.

## Cost interpretation

ChatGPT subscription-backed Codex usage does not expose an attributable
per-request invoice line in this path. P0-A therefore records subscription
cost as unavailable, never zero, and preserves elapsed time, token evidence
when exposed, and attempts/repair passes. The wizard does not request a plan
fee, billing period, or flat allocation.

OpenRouter is a future provider slice and canonical normalized reference-price
source for that slice. It may supply an attributable usage debit/charge only
for requests that traverse it and provide billing evidence; this is not an
upstream provider invoice. A non-OpenRouter Luna run may receive an
OpenRouter-equivalent reference only with an exact mapping, frozen pricing
snapshot, and token evidence; that value is not the ChatGPT bill. See
[`COST_MODEL.md`](../COST_MODEL.md) and [ADR 0011](0011-cloud-cost-evidence-and-openrouter-references.md).

## Challenge coverage

P0-A requires the live SUT to invoke Busy Intersection and produce complete
evidence whether the artifact passes or fails. The 5x5 Rush remains a
versioned descriptor/topology fixture in P0-A and becomes a live challenge in
P0-B. Deterministic artifacts remain the acceptance basis for evaluator
behavior.

## Consequences

- P0 has one concrete real integration instead of three simultaneous unknowns.
- Codex JSONL provides a documented event/usage source for the first adapter.
- ChatGPT authentication avoids requiring a Platform API key for the live P0
  smoke path while exercising honest unavailable-cost evidence.
- P0 does not prove real LM Studio lifecycle, local hardware cohorting, or
  metered API billing collection; those remain architecture-and-fixture tested.
- The `rb` wizard has one detected real client/provider/model path in P0 and
  should clearly label all other entries unsupported/TBD rather than implying
  partial production support.
- The exact ChatGPT plan entitlement, rate limits, and model availability are
  runtime observations and must not be inferred from authentication alone.
- Subscription/quota accounting is deferred until a separately approved policy
  has provider-reported evidence and clear semantics.

## Rejected alternatives

### OpenCode plus LM Studio as the first path

Useful for the eventual local track, but requires solving both a second
harness's configuration and a mutable local inference runtime before the core
contracts are proven.

### Codex CLI with an OpenAI Platform API key

Would provide metered API cost, but is a different authentication/billing path
from the requested ChatGPT-backed experience. It remains a future provider
adapter or provider mode.

### Multiple live SUT combinations in P0

Broadens coverage but obscures whether early failures come from the conductor,
adapter contracts, provider setup, or vendor-specific behavior.
