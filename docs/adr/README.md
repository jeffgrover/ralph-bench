# Architecture Decision Records

These records capture the foundational decisions approved for Ralph Bench P0-A.
They were accepted when implementation began on 2026-08-23. Superseded ADRs are
retained as historical decisions; the current cost decision is ADR 0011.

| ADR | Decision |
|---|---|
| [0001](0001-greenfield-repository.md) | Build Ralph Bench as a greenfield repository. |
| [0002](0002-immutable-run-bundles.md) | Make immutable run bundles the reporting boundary. |
| [0003](0003-sustainable-valid-throughput.md) | Use sustainable monitored throughput with separate validity evidence. |
| [0004](0004-controlled-and-native-loops.md) | Keep controlled and native agent loops as distinct tracks. |
| [0005](0005-rb-guided-experiment-authoring.md) | Use `rb` with client-first guided experiment authoring. |
| [0006](0006-centralized-configuration-lifecycle.md) | Centralize provider/client configuration ownership and cleanup. |
| [0007](0007-polymorphic-sut-adapters.md) | Compose harness, provider, and model adapter families polymorphically. |
| [0008](0008-p0-codex-chatgpt-luna-sut.md) | Use Codex CLI, ChatGPT access, and Luna for the P0 live SUT. |
| [0009](0009-one-real-implementation-per-p0-seam.md) | Keep proven contracts while building one real P0 implementation per seam. |
| [0010](0010-require-cloud-cost-evidence.md) | Require cost evidence for every cloud run; superseded by ADR 0011. |
| [0011](0011-cloud-cost-evidence-and-openrouter-references.md) | Preserve cloud cost evidence, use OpenRouter references explicitly, and defer subscription allocation. |
| [0012](0012-defer-strong-isolation-backends.md) | Use portable L0 protection in P0 and defer strong isolation-tool selection. |
| [0013](0013-minimal-gates-interface.md) | Replace the rich traffic bridge with evaluator-injected `gates/v1` arrivals, finishes, and monitoring. |
