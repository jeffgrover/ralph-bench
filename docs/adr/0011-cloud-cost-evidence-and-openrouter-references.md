# ADR 0011: Cloud Cost Evidence, OpenRouter References, and Subscription Deferral

**Status:** Accepted
**Date:** 2026-08-23

## Context

ADR 0010 required an operator-declared allocation of a flat subscription fee
for every cloud comparison. The allocation was an accounting view, not a
provider invoice, and the wizard experience showed that it created false
precision for ChatGPT-managed access that exposes no attributable per-request
charge.

Cloud routes also expose different evidence. A metered provider may report an
attributable charge, while OpenRouter can report the usage debit it attributes
to a request and publish mutable model pricing. A price calculated from that
catalog for a request sent through another provider is a reference, not a bill
from either OpenRouter or that provider.

## Decision

ADR 0010 is superseded for P0-A. Every cloud result preserves a typed,
nullable cost envelope with provenance and evidence references. It distinguishes:

- `actual_cost_usd`: an attributable charge from the route that actually
  served the inference. For an OpenRouter request, this means an OpenRouter
  usage debit/charge evidenced by the response or generation record; it must
  not be described as the upstream provider's invoice. Another provider or
  harness may supply its own attributable actual charge. When present,
  `actual_source` is required.
- `reference_cost_usd`: a reproducible normalized reference derived from an
  exact model mapping, a frozen pricing snapshot, and native token/usage
  evidence. The next provider slice uses OpenRouter's catalog as the
  canonical reference authority, but the field is generic and is paired with
  the required `reference_source`. For a non-OpenRouter request, the UI label
  is **OpenRouter-equivalent reference cost** and must not say “cost paid,”
  “actual cost,” or “OpenRouter bill.”
- `status`: `complete`, `provisional`, or `unavailable`, independent of which
  amount(s) are populated. The actual and reference amounts may coexist.
  `complete` and `provisional` require at least one sourced amount;
  `unavailable` requires both amounts and source fields to be `null` plus an
  explicit `unavailable_reason`.

OpenRouter is the canonical normalized reference-price catalog for the next
provider slice. A model mapping is valid only when the requested and canonical
IDs, snapshot digest/effective time, mapping rationale, and route or fallback
qualifiers are retained. Mutable catalog membership and pricing are snapshot
evidence, not timeless product facts. The current catalog and pricing fields
are documented by [OpenRouter's models endpoint reference](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties).

A reference calculation must account for every applicable priced component
that the selected route and usage evidence expose, including prompt,
completion, cache read/write, request, image, web-search, and internal
reasoning components, plus any documented price overrides or discounts. If a
component, modality, route, or native usage count is unsupported or ambiguous,
the reference is unavailable rather than silently under-counted. OpenRouter's
[usage-accounting documentation](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
is the source for the captured per-generation usage and cost evidence.

P0-A uses Codex CLI with ChatGPT-managed subscription access. It records
subscription cost as unavailable, preserves elapsed time, token evidence when
exposed, independent runs, and Ralph repair passes, and does not ask for a
plan fee, billing period, or synthetic per-attempt allocation. Subscription
and quota accounting are deferred to a separately versioned policy.

P0-A subscription results remain eligible for quality, throughput, time,
token, and attempt analysis, but are excluded from cost-based rankings. Cost
views and cost-to-green are rendered only for compatible cohorts with actual
or supported reference evidence; actual-charge and reference cohorts never
share a primary-cost ranking merely because both values are in USD.

Credentials remain outside experiment files and result bundles. OpenRouter
billing/reference support is the next provider implementation, not a P0-A
live requirement.

## Consequences

- P0-A authoring no longer asks operators to defend an arbitrary subscription
  allocation.
- Missing cost is visible as unavailable, never numeric zero.
- Actual usage debits and normalized references remain separately labeled and
  auditable; both may be retained in one result.
- Historical bundles are not rewritten when the future OpenRouter or
  subscription/quota schemas are implemented.
- P0-A can provide diagnostic and non-cost comparisons without pretending that
  its ChatGPT subscription path has a measured per-run price.

## Rejected alternatives

### Allocate a flat subscription fee across attempts in P0-A

This creates an operator-selected accounting number that looks like provider
spend and obscures the absence of a per-request bill.

### Treat included subscription usage as zero cost

This confuses marginal request charge with the economic cost of a plan. P0-A
uses unavailable, not zero.

### Treat an OpenRouter reference as a bill from another provider

OpenRouter can normalize a mapped model's price, but it cannot establish what
a request sent through another provider actually cost.
