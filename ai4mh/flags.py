# ai4mh/flags.py
# ─────────────────────────────────────────────────────────────────────────────
# Governance Flag Detection
#
# This module detects conditions that should modify how the system interprets
# a signal. Flags never suppress a signal — they reduce its weight and surface
# the reason to the human reviewer, who makes the final judgment.
#
# Core principle: the system must never hide its own uncertainty or limitations.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import re

import config


# ── DATA STRUCTURES ───────────────────────────────────────────────────────────

@dataclass
class Post:
    """A single social media post."""
    post_id: str
    account_id: str
    text: str
    timestamp: datetime
    county_fips: str
    account_age_days: int = 365     # default: established account
    account_karma: int = 100        # default: normal karma
    sentiment_score: float = 0.0   # populated by scoring module


@dataclass
class FlagResult:
    """
    The result of running all governance checks on a batch of posts.

    Attributes:
        active_flags: List of flag names currently active (e.g. ['bot_risk'])
        volume_discount: Multiplier applied to volume component (1.0 = no discount)
        plain_language_notes: Human-readable explanations for each flag
        discounted_posts: Posts that were flagged and have reduced weight
    """
    active_flags: List[str] = field(default_factory=list)
    volume_discount: float = 1.0
    plain_language_notes: List[str] = field(default_factory=list)
    discounted_posts: List[str] = field(default_factory=list)   # post_ids

    def has_flag(self, flag_name: str) -> bool:
        return flag_name in self.active_flags

    def add_flag(self, name: str, note: str) -> None:
        if name not in self.active_flags:
            self.active_flags.append(name)
        self.plain_language_notes.append(note)


# ── BOT DETECTION ─────────────────────────────────────────────────────────────

def detect_bot_activity(posts: List[Post]) -> FlagResult:
    """
    Detect coordinated inauthentic behavior.

    Two checks:
    1. Velocity filter — accounts posting too many crisis-language messages
       in a short window are suspicious. Their posts are included but discounted.
    2. Near-duplicate clustering — copy-paste campaigns are identified by
       text similarity. The cluster contributes one post-weight, not N.

    WHY: Bot activity inflates volume without reflecting genuine community
    distress. We discount rather than remove because a real person in crisis
    doesn't stop being in crisis because bots are also posting.
    """
    result = FlagResult()
    now = max(p.timestamp for p in posts) if posts else datetime.utcnow()
    window_start = now - timedelta(hours=24)

    # ── Check 1: Velocity filter ──────────────────────────────────────────────
    account_post_counts: Dict[str, int] = {}
    for post in posts:
        if post.timestamp >= window_start:
            account_post_counts[post.account_id] = (
                account_post_counts.get(post.account_id, 0) + 1
            )

    flagged_accounts = {
        acc for acc, count in account_post_counts.items()
        if count > config.BOT_VELOCITY_THRESHOLD
    }

    if flagged_accounts:
        flagged_post_ids = [
            p.post_id for p in posts if p.account_id in flagged_accounts
        ]
        result.discounted_posts.extend(flagged_post_ids)
        result.add_flag(
            "bot_risk",
            f"Velocity filter: {len(flagged_accounts)} account(s) posted more than "
            f"{config.BOT_VELOCITY_THRESHOLD} times in 24 hours. "
            f"{len(flagged_post_ids)} posts discounted."
        )

    # ── Check 2: Near-duplicate clustering ───────────────────────────────────
    # Simplified cosine similarity using word overlap (MVP implementation)
    # Full TF-IDF vectorization is in the roadmap
    recent_posts = [p for p in posts if p.timestamp >= now - timedelta(hours=6)]
    duplicate_ids = _find_near_duplicates(recent_posts)

    if duplicate_ids:
        result.discounted_posts.extend(duplicate_ids)
        result.add_flag(
            "bot_risk",
            f"Near-duplicate clustering: {len(duplicate_ids)} posts identified as "
            f"coordinated (high text similarity within 6 hours). "
            f"Cluster contributes 1 post-weight to volume."
        )

    # ── Apply volume discount if bot activity detected ────────────────────────
    unique_accounts = len(set(p.account_id for p in posts))
    if (result.has_flag("bot_risk") and
            unique_accounts < config.BOT_MIN_UNIQUE_ACCOUNTS):
        result.volume_discount = config.VOLUME_DISCOUNT_MULTIPLIER
        result.add_flag(
            "bot_risk",
            f"Low unique account diversity ({unique_accounts} accounts). "
            f"Volume component discounted by "
            f"{int((1 - config.VOLUME_DISCOUNT_MULTIPLIER) * 100)}%."
        )

    return result


def _find_near_duplicates(posts: List[Post]) -> List[str]:
    """
    Simple word-overlap similarity check.
    Returns post_ids of posts that are near-duplicates of another post.
    MVP implementation — roadmap item: replace with TF-IDF cosine similarity.
    """
    duplicate_ids = []
    texts = [(p.post_id, set(p.text.lower().split())) for p in posts]

    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            id_a, words_a = texts[i]
            id_b, words_b = texts[j]
            if not words_a or not words_b:
                continue
            # Jaccard similarity as MVP proxy for cosine similarity
            intersection = len(words_a & words_b)
            union = len(words_a | words_b)
            similarity = intersection / union if union > 0 else 0
            if similarity >= config.BOT_COSINE_SIMILARITY_THRESHOLD:
                if id_b not in duplicate_ids:
                    duplicate_ids.append(id_b)

    return duplicate_ids


# ── MEDIA SPIKE DETECTION ─────────────────────────────────────────────────────

# Media event registry — manually maintained by analysts.
# Format: list of dicts with 'event_id', 'description', 'timestamp'
# In production this would be loaded from a database.
MEDIA_EVENT_REGISTRY: List[Dict] = []


def register_media_event(event_id: str, description: str,
                          timestamp: datetime) -> None:
    """Add a known media event to the registry."""
    MEDIA_EVENT_REGISTRY.append({
        "event_id": event_id,
        "description": description,
        "timestamp": timestamp
    })


def detect_media_spike(posts: List[Post],
                        window_start: datetime) -> FlagResult:
    """
    Detect whether a volume spike is likely driven by media coverage
    rather than genuine community distress.

    Two checks:
    1. Temporal: spike timestamp aligns with a registered media event
    2. Linguistic register: posts classified as reportative (discussing
       news) rather than first-person distress

    WHY: The 2025 prototype flagged geospatial analysis as deferred due
    to privacy concerns. Media-driven spikes are a key reason naive
    geospatial signals are untrustworthy. We discount, not suppress —
    the human reviewer makes the final call.
    """
    result = FlagResult()

    # ── Check 1: Media event registry alignment ───────────────────────────────
    window_center = window_start + timedelta(
        hours=config.ANALYSIS_WINDOW_HOURS / 2
    )
    event_window = timedelta(hours=config.MEDIA_EVENT_WINDOW_HOURS)

    matching_events = [
        e for e in MEDIA_EVENT_REGISTRY
        if abs((e["timestamp"] - window_center).total_seconds()) <=
           event_window.total_seconds()
    ]

    if matching_events:
        event_names = ", ".join(e["description"] for e in matching_events)
        result.add_flag(
            "media_context",
            f"Volume spike aligns with registered media event(s): {event_names}. "
            f"Signal may reflect reactive discussion, not community distress. "
            f"Human reviewer should apply additional judgment."
        )
        # Note: we attach the flag but do NOT automatically discount for
        # media events — the human decides. This is intentional.
        # Only bot activity triggers automatic discounting.

    # ── Check 2: Linguistic register classification ───────────────────────────
    reportative_count = sum(
        1 for p in posts if _is_reportative(p.text)
    )
    reportative_ratio = reportative_count / len(posts) if posts else 0

    if reportative_ratio > 0.4:   # more than 40% of posts are reportative
        result.volume_discount = min(
            result.volume_discount,
            config.MEDIA_REPORTATIVE_WEIGHT
        )
        result.add_flag(
            "media_context",
            f"{int(reportative_ratio * 100)}% of posts classified as reportative "
            f"(discussing news rather than personal distress). "
            f"Volume component discounted to reflect genuine distress signal."
        )

    return result


def _is_reportative(text: str) -> bool:
    """
    Classify whether a post is reportative (discussing news about crisis)
    vs. first-person distress expression.

    MVP implementation using pattern matching.
    Roadmap: replace with fine-tuned classifier from 2025 BERT model.
    """
    text_lower = text.lower()

    # Reportative patterns — discussing events, not expressing distress
    reportative_patterns = [
        r"\bdid you (hear|see|read)\b",
        r"\bhave you (heard|seen)\b",
        r"\baccording to\b",
        r"\bbreaking( news)?\b",
        r"\bnews(report)?\b",
        r"\barticle (says|reports)\b",
        r"\breport(s|ing|ed)?\b",
        r"\bthey (say|said|found)\b",
        r"\bstory about\b",
    ]

    # First-person distress patterns — genuine personal expression
    firstperson_patterns = [
        r"\bi (can'?t|cannot|don'?t want to)\b",
        r"\bi (feel|felt|am feeling)\b",
        r"\bi (want to die|want to end)\b",
        r"\bkill myself\b",
        r"\bend (it|my life|everything)\b",
        r"\bno (reason|point) (to live|anymore)\b",
        r"\bi'?m so (depressed|hopeless|lost)\b",
    ]

    has_reportative = any(re.search(p, text_lower) for p in reportative_patterns)
    has_firstperson = any(re.search(p, text_lower) for p in firstperson_patterns)

    # If it has reportative markers but no first-person distress → reportative
    return has_reportative and not has_firstperson


# ── RURAL / SPARSE DATA DETECTION ─────────────────────────────────────────────

def detect_rural_sparse(county_fips: str, n_posts: int,
                         rucc_code: int) -> FlagResult:
    """
    Detect rural underrepresentation and sparse data conditions.

    WHY: Rural counties have structurally lower social media activity.
    This is not lower crisis risk — it's a data access inequality.
    The 2025 BERT model was trained on Reddit data which skews toward
    urban, young, English-speaking users. The model may not recognize
    how rural communities express distress.

    We NEVER silence rural signals. We route them to a dedicated queue
    with explicit uncertainty labeling and a bias disclosure note.
    """
    result = FlagResult()
    is_rural = rucc_code in config.RURAL_RUCC_CODES
    threshold = config.MIN_POSTS_RURAL if is_rural else config.MIN_POSTS_URBAN

    if n_posts < threshold:
        result.add_flag(
            "rural_sparse",
            f"Sample size below threshold ({n_posts} posts, minimum {threshold} "
            f"for {'rural' if is_rural else 'urban'} county). "
            f"Signal routed to sparse-data review queue. "
            f"Treat confidence estimate with additional caution."
        )

    if is_rural:
        result.add_flag(
            "rural_bias",
            f"Rural county (RUCC {rucc_code}). "
            f"Sentiment model trained predominantly on urban data — "
            f"crisis language patterns in this region may be underdetected. "
            f"Apply additional judgment beyond the CSS score."
        )

    return result


# ── COMBINED FLAG RUNNER ──────────────────────────────────────────────────────

def run_all_flags(posts: List[Post], county_fips: str,
                  rucc_code: int, window_start: datetime) -> FlagResult:
    """
    Run all governance checks and merge results into a single FlagResult.

    This is the main entry point called by the pipeline.
    """
    combined = FlagResult()

    bot_result   = detect_bot_activity(posts)
    media_result = detect_media_spike(posts, window_start)
    rural_result = detect_rural_sparse(county_fips, len(posts), rucc_code)

    # Merge flags
    for flag_result in [bot_result, media_result, rural_result]:
        combined.active_flags.extend(flag_result.active_flags)
        combined.plain_language_notes.extend(flag_result.plain_language_notes)
        combined.discounted_posts.extend(flag_result.discounted_posts)

    # Apply the most restrictive volume discount across all checks
    combined.volume_discount = min(
        bot_result.volume_discount,
        media_result.volume_discount
    )

    # Deduplicate flags
    combined.active_flags = list(set(combined.active_flags))
    combined.discounted_posts = list(set(combined.discounted_posts))

    return combined
