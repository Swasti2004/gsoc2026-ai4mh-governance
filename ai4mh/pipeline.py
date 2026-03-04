# ai4mh/pipeline.py
# ─────────────────────────────────────────────────────────────────────────────
# End-to-End Pipeline Orchestration
#
# This module ties everything together:
# flags → scoring → audit logging → escalation routing
#
# Run directly:  python -m ai4mh.pipeline
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
import csv
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path

import config
from ai4mh.flags import Post, run_all_flags
from ai4mh.scoring import evaluate_county, CSSResult, EscalationTier
from ai4mh.audit import AuditLogger, AnalystAction


# ── SAMPLE DATA LOADER ────────────────────────────────────────────────────────

def load_posts_from_csv(filepath: str) -> Dict[str, List[Post]]:
    """
    Load posts from CSV and group by county_fips.
    Expected columns: post_id, account_id, text, timestamp, county_fips,
                      account_age_days, account_karma
    """
    posts_by_county: Dict[str, List[Post]] = {}
    path = Path(filepath)

    if not path.exists():
        print(f"[WARNING] Data file not found: {filepath}")
        print("[INFO] Using built-in sample data instead.")
        return _generate_sample_data()

    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            post = Post(
                post_id=row["post_id"],
                account_id=row["account_id"],
                text=row["text"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                county_fips=row["county_fips"],
                account_age_days=int(row.get("account_age_days", 365)),
                account_karma=int(row.get("account_karma", 100)),
            )
            posts_by_county.setdefault(post.county_fips, []).append(post)

    return posts_by_county


def _generate_sample_data() -> Dict[str, List[Post]]:
    """
    Generate realistic sample posts for three Alabama counties.
    Demonstrates three scenarios: genuine crisis, media spike, rural sparse.
    """
    now = datetime.utcnow()

    # County 1 — Genuine crisis signal (Jefferson County, Birmingham)
    jefferson_posts = []
    crisis_texts = [
        "I can't do this anymore. Everything feels hopeless and I don't see a way out.",
        "Been having really dark thoughts lately. Can't sleep, can't eat. I'm exhausted.",
        "I don't want to be here anymore. The pain is too much.",
        "Feeling so depressed. I've lost the will to keep going.",
        "I'm so done with everything. I just want it to stop.",
        "Nobody understands what I'm going through. I feel completely alone.",
        "I've been thinking about ending it. I don't know what to do.",
        "Can't stop crying. I feel worthless and like a burden to everyone.",
        "The darkness is closing in. I can't fight it anymore.",
        "I'm struggling so much. I need help but don't know where to turn.",
    ] * 4  # 40 posts

    for i, text in enumerate(crisis_texts):
        jefferson_posts.append(Post(
            post_id=f"jeff_{i:03d}",
            account_id=f"user_{i % 25:04d}",
            text=text,
            timestamp=now - timedelta(hours=random.uniform(0, 72)),
            county_fips="01073",
            account_age_days=random.randint(90, 2000),
            account_karma=random.randint(50, 5000),
        ))

    # County 2 — Media-driven spike (Madison County, Huntsville)
    madison_posts = []
    media_texts = [
        "Did you hear about the suicide case reported in the news today? So sad.",
        "Breaking news: mental health crisis reported locally. Have you seen this?",
        "According to the article, there's been an increase in mental health issues.",
        "They said in the report that this is a growing problem in our community.",
        "Have you read the story about the mental health crisis? It's alarming.",
        "The news story today about depression is really eye-opening.",
        "Story about local mental health struggles trending on social media today.",
        "Did anyone else see that news report about the crisis hotline calls?",
    ] * 5  # 40 posts

    for i, text in enumerate(media_texts):
        madison_posts.append(Post(
            post_id=f"mad_{i:03d}",
            account_id=f"user_{i % 30:04d}",
            text=text,
            timestamp=now - timedelta(hours=random.uniform(0, 24)),
            county_fips="01089",
            account_age_days=random.randint(200, 3000),
            account_karma=random.randint(100, 8000),
        ))

    # County 3 — Rural sparse (Lowndes County, rural Alabama)
    lowndes_posts = []
    rural_texts = [
        "I'm not doing well. Really struggling out here and there's nowhere to go.",
        "Feeling real low. Nothing seems worth it anymore.",
        "Been a hard week. Can't shake this feeling of hopelessness.",
        "I'm hurting bad and don't know who to talk to.",
        "Things are real dark right now. I need help.",
        "I don't know how much longer I can keep going like this.",
        "Crying all day again. I'm so tired of feeling this way.",
        "I feel like giving up. Everything is too hard.",
    ]  # Only 8 posts — below rural threshold of 15

    for i, text in enumerate(rural_texts):
        lowndes_posts.append(Post(
            post_id=f"low_{i:03d}",
            account_id=f"user_{i:04d}",
            text=text,
            timestamp=now - timedelta(hours=random.uniform(0, 72)),
            county_fips="01085",
            account_age_days=random.randint(180, 1500),
            account_karma=random.randint(20, 500),
        ))

    return {
        "01073": jefferson_posts,   # Jefferson County — urban, crisis signal
        "01089": madison_posts,     # Madison County — urban, media spike
        "01085": lowndes_posts,     # Lowndes County — rural, sparse
    }


# ── COUNTY METADATA ───────────────────────────────────────────────────────────

COUNTY_METADATA = {
    "01073": {"name": "Jefferson County",  "rucc_code": 1, "baseline_mean": 25, "baseline_std": 8},
    "01089": {"name": "Madison County",    "rucc_code": 2, "baseline_mean": 20, "baseline_std": 6},
    "01085": {"name": "Lowndes County",    "rucc_code": 8, "baseline_mean": 5,  "baseline_std": 2},
    "01101": {"name": "Montgomery County", "rucc_code": 2, "baseline_mean": 18, "baseline_std": 5},
}


# ── MAIN PIPELINE ─────────────────────────────────────────────────────────────

def run_pipeline(data_path: str = "data/sample_posts.csv",
                 audit_path: Optional[str] = None) -> List[CSSResult]:
    """
    Run the full AI4MH governance pipeline.

    For each county with posts in the analysis window:
    1. Load and group posts
    2. Run governance flag detection
    3. Compute conditional CSS score
    4. Log audit record
    5. Print escalation summary

    Returns list of CSSResult for all evaluated counties.
    """
    print("\n" + "="*65)
    print("  AI4MH GOVERNANCE PIPELINE")
    print("  Mental Health Crisis Signal Evaluation")
    print("="*65)

    window_start = datetime.utcnow() - timedelta(hours=config.ANALYSIS_WINDOW_HOURS)
    logger = AuditLogger(audit_path)
    results = []

    posts_by_county = load_posts_from_csv(data_path)

    print(f"\n[INFO] Analysis window: {window_start.strftime('%Y-%m-%d %H:%M')} UTC "
          f"→ now (72 hours)")
    print(f"[INFO] Counties to evaluate: {len(posts_by_county)}\n")
    print("-"*65)

    for county_fips, posts in posts_by_county.items():
        meta = COUNTY_METADATA.get(county_fips, {
            "name": f"County {county_fips}",
            "rucc_code": 3,
            "baseline_mean": 15,
            "baseline_std": 5,
        })

        print(f"\n▶  {meta['name']} ({county_fips})")
        print(f"   Posts collected: {len(posts)}")

        # Step 1: Run all governance flags
        flag_result = run_all_flags(
            posts=posts,
            county_fips=county_fips,
            rucc_code=meta["rucc_code"],
            window_start=window_start,
        )

        if flag_result.active_flags:
            print(f"   Flags detected: {', '.join(flag_result.active_flags)}")
            print(f"   Volume discount: {flag_result.volume_discount:.0%}")

        # Step 2: Score the county
        result = evaluate_county(
            posts=posts,
            county_fips=county_fips,
            rucc_code=meta["rucc_code"],
            window_start=window_start,
            baseline_mean=meta["baseline_mean"],
            baseline_std=meta["baseline_std"],
            neighboring_scores=None,
            flag_result=flag_result,
        )

        # Step 3: Log to audit
        record = logger.log_evaluation(result)

        # Step 4: Print result
        print(f"\n   {result.summary()}")
        if result.routed_to_sparse_queue:
            print(f"   ⚠  ROUTED TO SPARSE-DATA REVIEW QUEUE")
        print(f"   Confidence: {result.confidence.plain_language}")
        print(f"   Audit ID: {record.event_id[:8]}...")

        results.append(result)

    # ── Escalation Summary ────────────────────────────────────────────────────
    print("\n" + "="*65)
    print("  ESCALATION SUMMARY")
    print("="*65)

    high     = [r for r in results if r.escalation_tier == EscalationTier.HIGH]
    moderate = [r for r in results if r.escalation_tier == EscalationTier.MODERATE]
    low      = [r for r in results if r.escalation_tier == EscalationTier.LOW]
    noise    = [r for r in results if r.escalation_tier == EscalationTier.NOISE]
    sparse   = [r for r in results if r.routed_to_sparse_queue]

    if high:
        print(f"\n🔴 HIGH — Immediate escalation required ({len(high)} county/ies):")
        for r in high:
            meta = COUNTY_METADATA.get(r.county_fips, {})
            print(f"   • {meta.get('name', r.county_fips)} | CSS={r.css:.2f}")

    if moderate:
        print(f"\n🟡 MODERATE — On-call analyst within 4 hours ({len(moderate)} county/ies):")
        for r in moderate:
            meta = COUNTY_METADATA.get(r.county_fips, {})
            print(f"   • {meta.get('name', r.county_fips)} | CSS={r.css:.2f}")

    if low:
        print(f"\n🟢 LOW — Daily review queue ({len(low)} county/ies)")

    if noise:
        print(f"\n⚪ NOISE — Archived ({len(noise)} county/ies)")

    if sparse:
        print(f"\n⚠  SPARSE DATA — Human review queue ({len(sparse)} county/ies):")
        for r in sparse:
            meta = COUNTY_METADATA.get(r.county_fips, {})
            print(f"   • {meta.get('name', r.county_fips)} | n={r.n_posts} posts")

    print(f"\n[INFO] All events logged to: {logger.log_path}")
    print("[INFO] No autonomous action taken. Human confirmation required.\n")

    return results


if __name__ == "__main__":
    run_pipeline()
