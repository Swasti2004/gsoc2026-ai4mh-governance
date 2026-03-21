# AI4MH — Governance Layer

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GSoC 2026](https://img.shields.io/badge/GSoC-2026-orange.svg)](https://summerofcode.withgoogle.com/)

**GSoC 2026 Contributor Selection Task**  
AI-Powered Behavioral Analysis for Mental Health Crisis Detection  
Organization: HumanAI | ISSR, University of Alabama  
Mentors: David M. White, MPH, MPA · Hailey Richardson · Dr. Andrea Underhill

---

Traditional public health data lags behind emerging crises by days or weeks. AI4MH compresses that detection window by analyzing aggregated social media sentiment at the county level. This repository implements the governance layer — the logic that determines whether a signal is trustworthy enough to escalate to a human reviewer.

> Not an AI that identifies at-risk individuals. Not a system that acts autonomously.  
> A tool that hands a clearly reasoned signal — with uncertainty attached — to a human who decides.

---

## What's Built

| Component | Status |
|---|---|
| Conditional CSS scoring | ✅ |
| Bot detection & media spike filtering | ✅ |
| Rural sparse data handling | ✅ |
| Immutable audit logging | ✅ |
| End-to-end walkthrough notebook | ✅ |
| Plotly Dash dashboard | 🔜 GSoC coding period |
| Geospatial heatmaps (GeoPandas + Folium) | 🔜 GSoC coding period |
| Live Reddit API integration | 🔜 GSoC coding period |

---

## Structure

```
ai4mh-governance/
├── ai4mh/
│   ├── scoring.py       — conditional CSS scoring
│   ├── flags.py         — bot, media, rural flag detection
│   ├── audit.py         — immutable audit logging
│   └── pipeline.py      — end-to-end orchestration
├── tests/               — 28 unit tests
├── docs/
│   ├── architecture.md                                    — full design rationale
│   └── AI4MH_GSoC2026_Swasti_Jain_Governance_Design.pdf  — contributor selection task submission
├── config.py            — all thresholds in one place
└── walkthrough.ipynb    — interactive end-to-end demo
```

The selection task PDF documents the complete governance design rationale, pseudocode, and architecture diagram.

---

## Quickstart

```bash
git clone https://github.com/Swasti2004/gsoc2026-ai4mh-governance.git
cd gsoc2026-ai4mh-governance
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m ai4mh.pipeline
python -m pytest tests/ -v
jupyter notebook walkthrough.ipynb
```

---

## Design Principles

- Sentiment anchors the signal. Volume and geography modify confidence — never the other way around.
- Rural counties are never silenced. Sparse data routes to human review, not silence.
- Uncertainty is never hidden. Every signal carries a confidence percentage, plain-language note, and visual tier.
- No score triggers action autonomously. Human confirmation is always required.

---

## Acknowledgements

Built on the [GSoC 2025 prototype](https://github.com/SparkFan626/GSoC2025_HumanAI_AI_Behavioral_Analysis_Demo) by Yixing (Spark) Fan, supervised by David M. White at ISSR, University of Alabama.

---

## 👩‍💻 Author

- **Name:** Swasti Jain
- **Email:** [jainswasti240@gmail.com](mailto:jainswasti240@gmail.com)
- **LinkedIn:** [linkedin.com/in/swasti-jain2004](https://www.linkedin.com/in/swasti-jain2004/)
- **GitHub:** [github.com/Swasti2004](https://github.com/Swasti2004)
- **For GSoC 2026**

---

MIT License
