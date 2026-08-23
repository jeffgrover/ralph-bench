# ADR 0010: Require Cost Evidence for Every Cloud Run

**Status:** Superseded by [ADR 0011](0011-cloud-cost-evidence-and-openrouter-references.md)
**Date:** 2026-08-23

## Context

Cloud cost is a primary Ralph Bench efficiency dimension. Flat ChatGPT
subscription access has a real plan cost even when an individual Codex request
does not produce a directly attributable invoice line. Describing those runs
as unmetered with USD unavailable would omit a required metric and repeat a
legacy ambiguity in which missing cost can look like numeric zero.

At the same time, billed cash, purchased credits, allocated subscription cost,
and public API list-price equivalents answer different questions and must not
be mixed without labels.

## Decision

Every cloud experiment declares a supported versioned cost policy, and every
cloud result carries a typed cost vector with nullable values, completeness,
provenance, confidence, and evidence references.

P0 implements `flat-subscription-attempt-pool/v1` for the live ChatGPT path.
The operator declares the USD amount one experiment should bear. Once every
expected terminal bundle is present, the catalog allocates that amount by
chargeable model-attempt count. All generated attempts and failed runs consume
weight. The allocated value is the primary P0 subscription cost.

Marginal cash charge and API list-price equivalent remain separate secondary
fields. Unknown values are null, never zero. An incomplete or open cost pool
may be displayed as provisional but cannot enter a final cost ranking.

The declared pool amount carries plan/period/source/allocation provenance and
is labeled accounting allocation rather than provider spend. The catalog
groups primary rankings by a mechanical comparability key; incompatible
subscription allocations, metered bills, and list-price equivalents do not
share a leaderboard.

The full policy and formulas are defined in
[`COST_MODEL.md`](../COST_MODEL.md).

## Consequences

- Subscription runs have an explicit, reviewable economic cost instead of a
  free/unpriced label.
- The operator must declare a defensible USD amount for the experiment pool;
  the wizard may help derive it from the real plan fee and benchmark share.
- Bundles preserve identical expected membership plus per-run attempt evidence;
  final allocation is derived at catalog time and never written back.
- Cost-to-green includes failed and repaired work.
- P0 needs cost fixtures for metered, subscription, provisional, and missing
  evidence even though only the subscription policy is live.
- Cross-provider comparisons can filter by compatible primary basis rather
  than pretending every cost field has the same provenance.

## Deferred extension

Published per-token input/output costs and percentage of daily, weekly, or
rolling plan quota consumed are a post-P0 reporting goal. The future extension
requires captured quota-window evidence and does not infer a precise allowance
from plan marketing alone.

## Rejected alternatives

### Treat included subscription usage as zero cost

Confuses marginal charge with economic cost and rewards prepaid access as if it
were free.

### Substitute API list price for the subscription charge

Useful as a normalized diagnostic but factually different from what the
operator paid.

### Exclude subscription runs from cost reporting

Violates the requirement that cost be a primary cloud metric and prevents the
P0 live SUT from exercising the real cost path.
