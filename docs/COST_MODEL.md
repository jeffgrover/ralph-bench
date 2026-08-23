# Cloud Cost and Price-Reference Model

**Status:** Accepted, as amended by [ADR 0011](adr/0011-cloud-cost-evidence-and-openrouter-references.md)
**Date:** 2026-08-23

## Decision summary

Ralph Bench records cost evidence without inventing a charge. A cloud run may
have an observed provider bill, a reproducible normalized price reference, or
no available cost. These are different facts and are never collapsed into one
leaderboard number.

OpenRouter is the canonical source for normalized cloud reference prices in
the next provider slice. Its mutable model catalog and pricing snapshot can
provide a common reference for models reached through OpenRouter and, with an
explicit model mapping, a reproducible equivalent for a run reached through
another provider. OpenRouter is not automatically the biller for an inference
that did not traverse OpenRouter.

P0-A does not implement OpenRouter billing or subscription accounting. The
live Codex + ChatGPT path records subscription billing as unavailable and
continues to report time, token usage when exposed, and attempts. An OpenRouter
provider implementation is the next provider slice, not a P0-A requirement.

## Cost evidence contract

Every cloud result carries a versioned cost envelope with at least:

- `status`: `complete`, `provisional`, or `unavailable`.
- `billing_mode`: `metered_api`, `flat_subscription`, `provider_credits`, or
  `other_declared`.
- `actual_cost_usd`: nullable route-attributable charge for this run. For an
  OpenRouter request this is an OpenRouter usage debit/charge evidenced by the
  response or generation record, not an upstream provider invoice. When
  present, `actual_source` is required.
- `reference_cost_usd`: nullable normalized comparison value. In the next
  provider slice, OpenRouter's catalog snapshot is the canonical reference
  authority; the field remains generic so the source is explicit rather than
  vendor-coupled. When present, `reference_source` is required.
- Price-source, model-mapping, token-usage, charge-scope, and evidence
  references, plus provenance, confidence, and explicit assumptions.

`status` is independent of the two amount fields: `complete` and `provisional`
require at least one sourced amount, and `actual_cost_usd` and
`reference_cost_usd` may coexist; `unavailable` requires both amounts and both
source fields to be `null` plus an explicit `unavailable_reason`.

Financial values use decimal strings or integer micros in interchange files,
not binary floating point. Unknown is `null`; zero is permitted only when
evidence establishes a real zero for that field. A report must label
`provider_billed`, `openrouter_reference`, `estimated`, and `unavailable`
separately.

`actual_cost_usd` may be populated only when:

1. The inference request traversed OpenRouter and OpenRouter supplied an
   attributable usage debit/charge, or
2. The actual inference provider or harness supplied an attributable charge
   for this run.

An operator-entered plan fee, a model's public list price, or a token estimate
does not become `actual_cost_usd`.

## OpenRouter reference semantics

The OpenRouter adapter captures a versioned pricing snapshot and records every
applicable pricing component exposed by the selected route, including prompt,
completion, cache read/write, request, image, web-search, and internal
reasoning rates, plus overrides or discounts. It also records the requested
model, canonical OpenRouter model, route/provider/fallback details, and any
route or discount qualifier. A derived reference cost is reproducible from:

```text
model mapping + pricing snapshot digest/effective time + complete supported
usage/component evidence
```

For a run that did not traverse OpenRouter, the result may expose
`reference_cost_usd` only when all three inputs are present. The UI label is
**OpenRouter-equivalent reference cost**, with the model mapping and snapshot
identifiers visible. It must not be labeled “cost paid,” “actual cost,” or
“OpenRouter bill.” The source field identifies the catalog snapshot used.

If a model cannot be mapped unambiguously, a priced component or route is not
supported, native usage counts are missing, or the pricing snapshot is stale
beyond the declared policy, the reference remains `null`/unavailable. The
catalog must not silently select a similarly named model, omit a surcharge, or
turn missing usage into zero.

For a request that did traverse OpenRouter, the adapter stores the generation
ID and raw response usage. When OpenRouter returns `usage.cost`, that value is
the attributable OpenRouter usage debit/charge; it is not an upstream provider
invoice. The independently derived reference value remains diagnostic.
OpenRouter's selected route or top-provider price can differ from the catalog
price, so the route/fallback evidence is required.
Token counts captured by another harness are not automatically OpenRouter
native counts; if used for an equivalent calculation they are marked
approximate.

## P0-A subscription behavior

P0-A uses Codex CLI with ChatGPT-managed subscription access. It does **not**
ask the operator to allocate a share of a plan fee, enter a billing period, or
confirm a synthetic per-attempt amount. Subscription and quota accounting are
deferred.

The P0-A bundle records:

- `billing_mode = "flat_subscription"`;
- `actual_cost_usd = null`, `reference_cost_usd = null`,
  `actual_source = null`, and `reference_source = null`;
- subscription cost status `unavailable` with an explanation;
- elapsed time, attempts/repair passes, and provider/harness token evidence
  when available; and
- the relevant provider, model, and authentication mode without credentials.

This is a complete diagnostic result, but it is not eligible for a cost-based
ranking. It remains eligible for quality, throughput, time, token, and
attempt comparisons. A future subscription policy may add provider-reported
quota-window evidence or an explicitly declared accounting view, but that is
a separately versioned design and must not rewrite historical bundles.

## Metered provider policy (next slices)

The first live metered implementation should be OpenRouter:

1. Query `GET /api/v1/models` with `OPENROUTER_API_KEY` held outside the
   repository and result bundles. Capture the selected model ID and freeze all
   applicable price components, fetch timestamp, response/digest, and any
   route or discount qualifiers used for discovery or execution.
2. Preserve OpenRouter's response usage (including native prompt, completion,
   reasoning, and cached-token counts) and the generation ID. If needed, fetch
   usage later by generation ID and retain the raw response as evidence.
3. Treat OpenRouter's returned `usage.cost` as an attributable OpenRouter
   usage debit/charge when present; otherwise set `actual_cost_usd` only from
   another attributable OpenRouter billing evidence source.
4. Otherwise calculate only the labeled reference value from the frozen rates
   and complete supported usage/component evidence. Unsupported or ambiguous
   reference cases remain unavailable.
5. Derive and retain the OpenRouter reference value from the snapshot and
   token evidence, clearly labeled as reference even when it matches the bill.

The catalog endpoint covers many models but is not a guarantee that every
provider model is available. A reference requires an exact, recorded model
mapping; an ambiguous or missing mapping leaves the reference unavailable.
For example, a current catalog snapshot may contain the OpenRouter ID
`openai/gpt-5.6-luna`, but a local or native-provider model ID must not be
assumed equivalent without mapping evidence. Record the snapshot fetch time
and digest because catalog membership and pricing can change. See [OpenRouter usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
and the [models endpoint reference](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties).

Other providers may later supply their own billing evidence. Their runs can
still receive an OpenRouter-equivalent reference when a reviewed mapping and
snapshot exist; they do not become OpenRouter-billed runs.

P0 exercises metered, subscription, provisional, and missing-evidence paths
with fixtures as useful, but implements no live API-key provider, billing API,
invoice import, currency conversion, or quota normalization.

## Comparability and reporting

The catalog keeps separate cohorts for:

- route-attributable `actual_cost_usd` (including an OpenRouter usage debit);
- upstream-provider invoice evidence, when separately available;
- OpenRouter-equivalent reference cost; and
- unavailable cost.

Reference costs are comparable only when model mappings, pricing snapshot
version, all applicable pricing components, token accounting, currency, and
charge scope are compatible. A
reference cohort must never be merged with an actual-bill cohort merely because
both values are denominated in USD. P0-A shows cost as unavailable for the
live subscription path and does not render a cost leaderboard.

The report should prefer a compact explanation over a fabricated scalar:

```text
Cost: unavailable (ChatGPT subscription; P0-A does not allocate plan fees)
Time: 184 s    Attempts: 2    Tokens: provider-reported/estimated
```

## Deferred subscription and quota accounting

A future `QuotaEvidence` extension may show provider-reported before/after
quota state, window type, remaining units, reset time, plan tier, provenance,
and confidence. It must not infer a precise allowance solely from marketing
limits or allocate a personal subscription across experiments without an
explicit, separately approved policy.

## OpenRouter slice requirements

- What snapshot freshness and route/fallback evidence are required before a
  reference becomes comparable rather than approximate?
- Should a later billing endpoint reconcile or supersede response `usage.cost`,
  and how should retries or provider credits be represented?
- Which cross-provider model mappings are reviewed as exact, and which must be
  marked approximate or left unavailable?
