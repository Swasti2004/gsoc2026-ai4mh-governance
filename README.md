# AI4MH — Governance Layer
### AI-Powered Mental Health Crisis Detection | GSoC 2026

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GSoC 2026](https://img.shields.io/badge/GSoC-2026-orange.svg)](https://summerofcode.withgoogle.com/)

> **GSoC 2026 Contributor Selection Task** — This repository was built as part of the selection process for the AI4MH project under HumanAI / ISSR, University of Alabama.

**Organization:** Institute for Social Science Research (ISSR), University of Alabama  
**Mentors:** David M. White, MPH, MPA & Dr. Andrea Underhill
**Project:** AI-Powered Behavioral Analysis for Suicide Prevention & Mental Health Crisis Detection

---

## What This Project Does

AI4MH monitors aggregated public sentiment across Alabama counties to detect emerging mental
health and substance use crises *before* they appear in hospital admissions data.

The 2025 GSoC prototype built the data ingestion, BERT-based risk classification, and sentiment
analysis pipeline. **This repository implements the governance layer** — the logic that determines
whether a signal is trustworthy enough to escalate to a human reviewer, and ensures that every
decision the system makes is transparent, auditable, and bias-aware.

> The system's north star: **a trend intelligence tool for public health decision-makers.**
> Not an AI that identifies at-risk individuals. Not a system that acts autonomously.
> A tool that hands a clearly reasoned signal — with uncertainty attached — to a human who decides.

---

## The Core Problem It Solves

Traditional public health data (hospital admissions, overdose reports) lags behind actual crisis
emergence by days or weeks. AI4MH compresses that detection window by analyzing social media
language patterns at the county level — but only if the signal can be trusted.

**This governance layer answers: "Is this signal trustworthy enough to act on?"**

---

## Architecture Overview

```
Raw Data (Reddit, Google Trends, Crisis Hotlines)
        ↓
Data Ingestion & Cleaning
(deduplication, bot velocity filter, EWMA smoothing)
        ↓
Three Signal Components
  ├── Sentiment Intensity  ← ANCHOR (VADER / BERT)
  ├── Volume Spike         ← CONFIDENCE MODIFIER
  └── Geographic Clustering← CORROBORATING MODIFIER
        ↓
Conditional CSS Scoring
(sentiment anchors; volume/geo modify confidence)
        ↓
Governance Flags
(bot_risk | media_context | rural_sparse | data_discounted)
        ↓
Escalation Tiers
  ├── HIGH     → Senior analyst, immediate
  ├── MODERATE → On-call analyst, 4 hours
  ├── LOW      → Daily review queue
  └── NOISE    → Archived
        ↓
Human Reviewer
(skilled analyst + authority + full evidence)
        ↓
Audit Log ←→ Feedback Loop (improves thresholds over time)
```

See [`docs/architecture.md`](docs/architecture.md) for full design rationale.

---

## Key Design Decisions

**1. Sentiment is the anchor signal, not one of three equal inputs.**
A volume spike caused by a bot campaign tells you nothing about real distress. Sentiment directly
reflects the language people are using. So sentiment anchors the score; volume and geography
modify confidence in that anchor.

**2. Rural counties are never silenced.**
Counties with fewer posts than the minimum threshold are routed to a dedicated sparse-data review
queue with explicit uncertainty labeling — not dropped. Silence is not a governance solution.

**3. The system never hides its own uncertainty.**
Every signal includes a confidence percentage, a plain-language explanation, and a visual tier.
A reviewer who sees only a red alert with no context is not exercising judgment — they are
rubber-stamping the algorithm.

**4. No score autonomously triggers action.**
The CSS is a decision-support signal, not a decision. Human confirmation is required before
any intervention action is taken.

---

## Project Structure

```
gsoc2026-ai4mh-governance/
├── README.md               ← You are here
├── requirements.txt        ← Python dependencies
├── config.py               ← All thresholds and constants in one place
├── walkthrough.ipynb       ← End-to-end interactive walkthrough
├── .gitignore
│
├── ai4mh/                  ← Core package
│   ├── __init__.py
│   ├── scoring.py          ← Conditional CSS scoring logic
│   ├── flags.py            ← Governance flag detection
│   ├── audit.py            ← Immutable audit logging
│   └── pipeline.py         ← End-to-end orchestration
│
├── data/
│   └── sample_posts.csv    ← Sample data for testing
│
├── tests/
│   ├── test_scoring.py     ← Unit tests for CSS logic
│   └── test_flags.py       ← Unit tests for flag detection
│
└── docs/
    └── architecture.md     ← Full design rationale
```

---

## Quickstart

```bash
# 1. Clone the repo
git clone https://github.com/Swasti2004/gsoc2026-ai4mh-governance.git
cd gsoc2026-ai4mh-governance

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the pipeline on sample data
python -m ai4mh.pipeline

# 5. Run tests
python -m pytest tests/ -v

# 6. Open the walkthrough notebook
jupyter notebook walkthrough.ipynb
```

---

## MVP Scope (Current)

| Component | Status | Notes |
|---|---|---|
| CSS conditional scoring | ✅ Complete | Sentiment anchor + volume/geo modifiers |
| Bot detection flags | ✅ Complete | Velocity filter + near-duplicate clustering |
| Media spike detection | ✅ Complete | Temporal pattern + linguistic register |
| Rural sparse data handling | ✅ Complete | Tiered thresholds + dedicated queue |
| Audit logging | ✅ Complete | Immutable JSON records |
| End-to-end walkthrough | ✅ Complete | Jupyter notebook with visible outputs |
| Sentiment layer | ✅ VADER (MVP) | BERT integration planned — see roadmap |
| Dashboard UI | 🔜 Roadmap | Plotly Dash planned |
| Real Reddit API | 🔜 Roadmap | PRAW integration planned |
| Geospatial heatmaps | 🔜 Roadmap | GeoPandas + Folium planned |

---

## Roadmap (GSoC Coding Period)

- [ ] Replace VADER with fine-tuned BERT classifier from 2025 prototype
- [ ] Integrate Reddit API (PRAW) for live data ingestion
- [ ] Build Plotly Dash dashboard with real-time county heatmaps
- [ ] Add GeoPandas + Folium geospatial visualization
- [ ] Implement Moran's I geographic clustering (currently mocked)
- [ ] Quarterly equity audit reports (rural vs. urban escalation rates)
- [ ] Multi-source signal fusion (211 call volume, ADPH ED data)

---

## Ethical Commitments

- **No individual identification.** The system operates at county-level aggregation only.
- **No autonomous action.** Every escalation requires human confirmation.
- **Bias transparency.** Rural and underrepresented communities receive explicit uncertainty
  labeling, not silence.
- **Full auditability.** Every decision is logged with complete provenance.

---

## Acknowledgements

This project builds directly on the [GSoC 2025 AI4MH prototype](https://github.com/SparkFan626/gsoc2025-ai4mh)
by Yixing (Spark) Fan and Vishnu Sankhyan, supervised by David M. White at ISSR, University of Alabama.
The 2025 team built the BERT classifier, VADER sentiment pipeline, and unified crisis dataset that
this governance layer is designed to operate on top of.

---

## 👩‍💻 Author

- **Name:** Swasti Jain
- **Email:** [jainswasti240@gmail.com](mailto:jainswasti240@gmail.com)
- **LinkedIn:** [linkedin.com/in/swasti-jain2004](https://www.linkedin.com/in/swasti-jain2004/)
- **GitHub:** [github.com/Swasti2004](https://github.com/Swasti2004)
- **For GSoC 2026**

---

## License

MIT License — see [LICENSE](LICENSE)
