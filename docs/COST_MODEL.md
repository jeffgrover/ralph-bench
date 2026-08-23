# Cloud and Subscription Cost Model

**Status:** Proposed
**Date:** 2026-08-23

## Decision summary

Cost is required for every cloud comparison, including flat-subscription
access. A missing provider charge must never become numeric zero, and a
subscription must not be described as free merely because an individual
request has no invoice line.

Ralph Bench keeps these concepts separate:

| Field | Unit | Meaning |
|---|---|---|
| `primary_cost_usd` | USD | Cost used for the run's declared comparison cohort. |
| `provider_billed_usd` | USD | Charge attributed to the run by a provider or harness. |
| `marginal_cash_usd` | USD | Incremental cash charge caused by the run, when observable. |
| `subscription_allocated_usd` | USD | Declared share of a flat plan/campaign cost. |
| `list_price_equivalent_usd` | USD | What observed usage would cost under a versioned public API table; diagnostic, not billed cash. |
| `provider_credits_reported` | provider units | Credits attributed to the run by the provider. |
| `credit_equivalent` | derived units | Token-derived usage weight under a versioned public rate card; not an observed debit. |

These values are not interchangeable. Reports show basis and provenance rather
than collapsing them into one unexplained number.

## Cost evidence contract

Every cloud result carries versioned cost evidence with at least:

- `status`: `complete`, `provisional`, or `incomplete`.
- `billing_mode`: `metered_api`, `flat_subscription`, `provider_credits`, or
  `other_declared`.
- `primary_basis`: the field used as `primary_cost_usd`.
- Nullable decimal USD fields and separately typed non-USD usage fields.
- Cost-policy, price/rate-table, allocation-pool, and charge-scope identifiers.
- Evidence references, provenance, confidence, and explicit assumptions.
- Effective provider, service tier, model, and billing period without account
  secrets.

Financial values use decimal strings or integer micros in interchange files,
not binary floating point. Unknown is `null`; zero is permitted only when
evidence establishes a real zero for that particular field.

An official cloud comparison requires a complete derived cost record and
non-null `primary_cost_usd`. `rb run` rejects a cloud experiment with no
supported cost policy. A post-run evidence failure is preserved as incomplete
rather than discarded.

## Bundle evidence versus derived cost

The immutable per-run bundle stores `RunCostEvidence`:

- The declared policy and pool identity.
- Pool scope, cost, expected run IDs, and membership digest.
- Chargeable attempt count and attempt references.
- Any provider-attributed cash, credit, token, or usage evidence.
- Provisional/incomplete status and assumptions.

The rebuildable catalog creates a `DerivedCostRecord` after it validates and
closes the pool. That record contains final `subscription_allocated_usd` and
`primary_cost_usd`. The reporter never writes the final value back into source
bundles.

This split makes allocation reproducible without weakening bundle immutability.
The bundle set remains the authoritative input; the catalog is disposable.

## P0 concrete policy: flat subscription attempt pool

P0 implements one real policy for Codex + ChatGPT + Luna:

```text
flat-subscription-attempt-pool/v1
```

P0 narrows a pool to one execution of one experiment: a single SUT, challenge,
and declared repetition set. The operator declares:

- Stable pool ID.
- `pool_scope = "experiment"`.
- USD amount assigned to this experiment as `pool_cost_usd`.
- Billing-period cost, benchmark allocation fraction, service-plan ID,
  `pool_cost_source`, and allocation rationale that produced that amount.
- Billing/campaign start and end for provenance.
- Closure rule `all_expected_runs_terminal`.

`pool_cost_usd` is a declared accounting allocation, not an observed provider
bill. P0 validates it as the billing-period cost multiplied by the declared
benchmark fraction, with versioned decimal rounding. The wizard displays and
reconfirms every input. It must not infer the plan from login status or silently
assign 100% of a personal subscription. P0 is USD-only and rejects a different
currency instead of performing an implicit conversion.

Zero is accepted only with evidence for a genuinely zero-price/free plan under
the selected source class. A manually typed zero with no plan/source evidence
is incomplete.

### Chargeable attempt unit

The primary P0 allocation weight is deliberately simple and attributable:

```text
one conductor-admitted model invocation = one chargeable attempt unit
```

The conductor emits `model_invocation.started` only after preflight succeeds,
the Codex process has spawned, and the prompt has been made available to that
process. From that point the request may have reached the service, so the unit
is charged conservatively even if authentication, networking, JSONL capture,
or the process later fails. A process-spawn or preflight failure before that
event has zero units. Every attempt records `generation_started_evidence` and
`charge_basis = "conservative_invocation_started"`; ambiguous post-spawn cases
are charged rather than undercounted.

It includes attempts that later pass, fail, time out, are aborted, become
tainted, or end in an infrastructure error after invocation. Browser judging,
traffic simulation, bundling, and report generation are outside this
model-subscription charge scope and are timed separately.

A repaired run normally has two units; a first-attempt green has one. This
ensures retries and failed work consume allocated cost even when Codex does not
expose reliable per-run credit debits.

### Pool allocation

When the pool closes:

```text
subscription_allocated_usd(run) =
    pool_cost_usd
  * run_chargeable_attempt_units
  / sum(chargeable_attempt_units for every expected run)
```

Every generated run remains in the denominator regardless of score validity or
outcome. Only pre-generation attempts have zero weight. A pool with no
chargeable attempts cannot be allocated and remains incomplete.

For the P0 experiment cohort:

```text
cost_to_green =
    sum(primary cost of every chargeable run in the cohort)
  / count(accepted green runs)
```

If generated runs exist but none are green, cost-to-green is undefined and the
complete allocated pool amount is shown. If every expected run fails before a
chargeable invocation, the pool cannot close and no allocated amount or
cost-to-green is reported. A successful-only mean that drops failed or tainted
generated runs is prohibited.

### Deterministic membership and closure

P0 preserves the two-command workflow; no manual third cost command is needed:

1. Before execution, the conductor expands repetitions, assigns every run ID,
   and records the expected member list and digest.
2. Every member bundle carries the same pool declaration, expected IDs, and
   digest plus its own chargeable-attempt evidence.
3. `rb build` groups bundles by pool ID and verifies that declarations agree,
   every expected terminal bundle is present exactly once, the membership
   digest matches, currency is USD, every member has complete and
   non-contradictory charge evidence, and total attempt weight is nonzero.
4. Only then does the catalog mark the pool closed and derive final run costs.
   Missing, late, duplicate, or contradictory members keep the pool
   provisional/incomplete and out of the final cost ranking.

This makes closure a deterministic consequence of the immutable inputs. A
later monthly or cross-experiment accounting pool would require a separate
versioned closure manifest and is post-P0.

### Example experiment fragment

```toml
[cost]
policy = "flat-subscription-attempt-pool/v1"
pool_id = "chatgpt-luna-intersection-pilot-01"
pool_scope = "experiment"
currency = "USD"
service_plan = "chatgpt-plus"
billing_period_cost_usd = "20.00"
benchmark_allocation_fraction = "1.0"
pool_cost_usd = "20.00"
pool_cost_source = "operator_attested_period_charge"
allocation_rationale = "dedicated_benchmark_period"
billing_period_start = "2026-08-01"
billing_period_end = "2026-08-31"
closure = "all_expected_runs_terminal"
```

The amount is illustrative. The operator supplies the actual USD amount that
this experiment should bear.

## Comparability and labeling

The derived catalog creates a mechanical cost comparability key from billing
mode, policy/version, currency, pool scope, pool-cost source class, allocation
basis/fraction, and charge scope. P0 ranks subscription costs only within a
matching key; incompatible pools appear in separate cohorts with a “not
comparable” label. Metered provider cash and API list-price equivalents never
enter the attempt-allocation cohort merely because all use USD.

The UI label is **Allocated subscription USD per chargeable attempt/task** and
states that it is declared experiment accounting, not the measured price of a
model request. Raw tokens, reported credits, and other usage stay separate.

## Secondary usage evidence

P0 preserves raw Codex token/turn/tool evidence when available, but none is
required to allocate the flat subscription under the primary attempt policy.

Provider-reported credits may be stored only when they are attributable to the
run. An account/window-level `/status` or dashboard delta is not a precise
per-run debit unless benchmark usage is serialized/dedicated and the evidence
supports that attribution. Token-derived ChatGPT credit equivalents must use a
versioned rate card and remain labeled estimated; they never become
`provider_credits_reported`.

The cost vector reserves `list_price_equivalent_usd`, but the live P0 path does
not promise a published per-token breakdown or use API pricing as the
subscription bill. P0 may exercise that field with deterministic fixtures.

Official sources checked for the contract:

- [ChatGPT and Codex pricing, plan fees, usage, and credit rate card](https://learn.chatgpt.com/docs/pricing)
- [GPT-5.6 Luna API token pricing](https://developers.openai.com/api/docs/models/gpt-5.6-luna)

## Future metered providers

The same vector supports a future metered API provider:

1. Prefer a provider-attributed billed amount.
2. Otherwise derive cost from complete token/tool usage and a versioned price
   table, labeling it derived.
3. Keep provider credits and list-price equivalent separate.
4. Mark the result incomplete if a required charge class cannot be observed or
   derived.

P0 exercises these paths with fixtures only. It does not implement a live API
key provider, billing API, invoice import, multi-currency conversion, purchased
credit reconciliation, or account-wide attribution.

## Post-P0 token-rate and quota-burden stretch goal

A future `QuotaEvidence` extension should show both published input/cached/
output rates and the share of a plan's rolling or fixed quota consumed by a
run. Candidate fields include window type, window start/end, quota units,
before/after remaining values, consumed percentage, reset time, plan tier,
provenance, and confidence.

This must use provider-reported or captured before/after quota state, not infer
a precise allowance solely from marketing limits. ChatGPT limits can vary by
plan and window; current documentation directs users to the usage dashboard or
`/status` for current remaining limits. P0 implements no quota probing,
daily/weekly normalization, multi-plan comparison, or user-facing published
per-token cost view.

## P0 acceptance tests

- A cloud experiment with no supported cost policy fails validation.
- Missing monetary evidence remains null/incomplete rather than `0.0`.
- Pool membership and chargeable-attempt evidence survive passing, failing,
  aborted, tainted, and post-generation infrastructure outcomes.
- A pre-invocation failure receives zero units; a spawned/admitted ambiguous
  invocation is charged conservatively; a repair consumes a second unit.
- Closing a pool allocates exactly `pool_cost_usd`, within declared decimal
  rounding rules.
- Missing/duplicate members, conflicting or incomplete charge evidence, zero
  total weight, and non-USD currency prevent closure.
- Pool cost has source/plan/allocation provenance; an unevidenced zero is
  rejected.
- Incompatible comparability keys never share a primary-cost ranking.
- The same closed bundle set produces the same derived cost records and site.
- Final catalog allocation never mutates a bundle.
- Provider-reported credits, derived credit equivalent, API list-price
  equivalent, and allocated subscription USD cannot be mislabeled as one
  another.
