# Architecture & Design Rationale

## Why This System Is Designed the Way It Is

This document explains the reasoning behind every major design decision.
These are not arbitrary choices — each one reflects a specific constraint
imposed by the public health environment this system operates in.

---

## The North Star

> A trend intelligence tool for public health decision-makers.
> Not an AI that identifies at-risk individuals.
> Not a system that acts autonomously.
> A tool that hands a clearly reasoned signal — with uncertainty attached —
> to a human who decides.

---

## Core Design Principles

### 1. Sentiment anchors. Volume and geography modify confidence.

A simple weighted average of three signals implies they are equally
trustworthy at all times. They are not.

- A volume spike from coordinated bot activity tells you nothing about
  real community distress.
- Geographic clustering amplifies confidence but its absence doesn't
  mean there's no crisis — it might just mean neighboring counties
  are also underreporting.
- Extreme sentiment (BERT/VADER score > 0.85) should stand alone,
  because a genuine crisis doesn't stop being a crisis because fewer
  people are posting about it.

**Implementation:** Conditional weighting in `scoring.py:evaluate_county()`

---

### 2. Rural counties are never silenced.

Rural Alabama counties have structurally lower social media activity.
This is not lower crisis risk — it's a data access inequality.

If a county doesn't reach the minimum post threshold, the wrong response
is to drop it. A rural county with 12 posts all expressing explicit
crisis language is more important to surface to a human reviewer than
an urban county with 200 posts of mild negativity.

**Implementation:** Sparse-data queue routing in `scoring.py`,
`detect_rural_sparse()` in `flags.py`

---

### 3. The system must never hide its uncertainty.

Every signal surfaces three simultaneous uncertainty channels:
- **Percentage confidence** — how much do the three components agree?
- **Plain language explanation** — what's driving this, and what caveats apply?
- **Visual tier** — color-coded, impossible to miss on a dashboard

A reviewer who sees only a red alert with no context is not exercising
judgment — they are rubber-stamping the algorithm.

**Implementation:** `ConfidenceEstimate` dataclass in `scoring.py`

---

### 4. Discount, don't delete.

When bot activity or media-driven spikes are detected, the temptation
is to remove those posts from the analysis. We don't do this.

Removing posts assumes the governance flag is always right. A real person
in crisis doesn't stop being in crisis because bots are also posting
during the same media event.

Instead: reduce the volume component weight and surface the reason to
the reviewer. The human decides whether to trust the discounted signal.

**Implementation:** `volume_discount` field in `FlagResult`, applied in
`evaluate_county()` step 3.

---

### 5. No autonomous action. Ever.

The CSS score is a decision-support signal, not a decision.

No threshold value should autonomously trigger resource deployment,
community notification, or contact with individuals. The escalation
tiers route signals to human reviewers — they do not trigger actions.

**Implementation:** `pipeline.py` ends with escalation summaries and
explicit note: "No autonomous action taken. Human confirmation required."

---

## Component Interactions

```
Post data
    │
    ▼
flags.run_all_flags()
    ├── detect_bot_activity()     → FlagResult (bot_risk, volume_discount)
    ├── detect_media_spike()      → FlagResult (media_context, volume_discount)
    └── detect_rural_sparse()     → FlagResult (rural_sparse, rural_bias)
    │
    ▼ FlagResult (merged)
    │
scoring.evaluate_county()
    ├── Sample size gate          → sparse queue if below threshold
    ├── compute_sentiment_score() → EWMA-smoothed VADER score
    ├── compute_volume_score()    → normalized Z-score
    ├── compute_geography_score() → neighbor mean (MVP) / Moran's I (roadmap)
    ├── Conditional CSS weighting → extreme sentiment standalone; else weighted
    ├── compute_confidence()      → 3-channel uncertainty estimate
    └── classify_tier()           → HIGH / MODERATE / LOW / NOISE
    │
    ▼ CSSResult
    │
audit.AuditLogger.log_evaluation()
    └── Immutable JSONL record
```

---

## Roadmap: What's Not Built Yet

| Component | Current State | Planned |
|---|---|---|
| Sentiment model | VADER (MVP) | BERT from 2025 prototype |
| Geographic clustering | Neighbor mean proxy | Moran's I with GeoPandas |
| Bot detection similarity | Jaccard word overlap | TF-IDF cosine similarity |
| Media event registry | In-memory list | Database-backed, analyst UI |
| Dashboard | CLI output | Plotly Dash with county heatmaps |
| Data source | Sample CSV | Reddit API (PRAW) |
| Rural bias mitigation | Transparency + flagging | Targeted retraining data |
| Equity audit | Not yet built | Quarterly urban/rural comparison reports |

---

## Data Privacy Commitments

The 2025 prototype team explicitly deferred geospatial analysis due to
privacy concerns. This governance layer addresses those concerns:

- **No individual identification.** County-level aggregation only.
- **No storage of raw post text** in audit logs — only derived scores.
- **De-identified post samples** shown to analysts for review context.
- **Public data only** — Reddit posts are publicly accessible under
  Reddit's terms of service for research purposes.
