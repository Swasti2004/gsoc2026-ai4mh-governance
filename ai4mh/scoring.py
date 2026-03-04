# ai4mh/scoring.py
# ─────────────────────────────────────────────────────────────────────────────
# Crisis Signal Scoring — Conditional CSS Framework
#
# This module implements the core signal scoring logic.
# Key design decision: sentiment ANCHORS the score.
# Volume and geography MODIFY confidence in that anchor.
# They are not three equal inputs to a weighted average.
#
# WHY CONDITIONAL WEIGHTING:
# A weighted average implies all three signals are equally trustworthy at
# all times. They are not. A volume spike from bots tells you nothing about
# real distress. Extreme sentiment stands alone. Moderate sentiment needs
# corroboration. This conditional logic reflects that reality.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from enum import Enum
import statistics

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _analyzer = SentimentIntensityAnalyzer()
    _VADER_AVAILABLE = True
except ImportError:
    _analyzer = None
    _VADER_AVAILABLE = False

import config
from ai4mh.flags import Post, FlagResult


# ── ESCALATION TIERS ──────────────────────────────────────────────────────────

class EscalationTier(str, Enum):
    HIGH     = "HIGH"       # Immediate escalation — senior analyst
    MODERATE = "MODERATE"   # On-call analyst within 4 hours
    LOW      = "LOW"        # Daily review queue
    NOISE    = "NOISE"      # Archived, no escalation


# ── RESULT STRUCTURES ─────────────────────────────────────────────────────────

@dataclass
class ComponentScores:
    """Individual component scores before combining into CSS."""
    sentiment: float        # [0, 1] — higher = more crisis-related distress
    volume: float           # [0, 1] — normalized volume Z-score
    geography: float        # [0, 1] — geographic clustering (Moran's I, mocked MVP)
    volume_adjusted: float  # volume after applying flag-based discount


@dataclass
class ConfidenceEstimate:
    """
    Three-channel uncertainty communication.
    A public health officer needs uncertainty to be impossible to miss
    and impossible to misinterpret — hence three simultaneous channels.
    """
    percentage: float           # [0, 1] — overall confidence
    plain_language: str         # one-line human-readable explanation
    visual_tier: str            # RED / AMBER / YELLOW / GRAY


@dataclass
class CSSResult:
    """
    Complete result of the CSS scoring pipeline for one county/window.

    This is everything the human reviewer needs to make an informed decision.
    No information is hidden or summarized away.
    """
    county_fips: str
    window_start: datetime
    window_end: datetime
    n_posts: int

    # Core score
    css: float
    escalation_tier: EscalationTier

    # Component breakdown — reviewer can see what drove the score
    components: ComponentScores

    # Governance context
    flags: FlagResult
    confidence: ConfidenceEstimate

    # Routing
    routed_to_sparse_queue: bool = False

    def is_escalated(self) -> bool:
        return self.escalation_tier in (
            EscalationTier.HIGH, EscalationTier.MODERATE
        )

    def summary(self) -> str:
        """One-line summary for dashboard display."""
        tier_emoji = {
            EscalationTier.HIGH:     "🔴",
            EscalationTier.MODERATE: "🟡",
            EscalationTier.LOW:      "🟢",
            EscalationTier.NOISE:    "⚪",
        }
        flags_str = (
            f" | Flags: {', '.join(self.flags.active_flags)}"
            if self.flags.active_flags else ""
        )
        return (
            f"{tier_emoji[self.escalation_tier]} {self.escalation_tier.value} "
            f"| County {self.county_fips} | CSS={self.css:.2f} "
            f"| Confidence={self.confidence.percentage:.0%} "
            f"| n={self.n_posts}{flags_str}"
        )


# ── SENTIMENT SCORING ─────────────────────────────────────────────────────────

def compute_sentiment_score(posts: List[Post]) -> Tuple[float, List[float]]:
    """
    Compute sentiment intensity using VADER.

    Returns:
        (smoothed_score, raw_scores_per_post)

    VADER produces a compound score from -1 (most negative) to +1 (most positive).
    We invert and normalize to [0, 1] where 1 = maximum crisis-level distress.

    EWMA smoothing is applied to dampen single-post outliers while preserving
    genuine multi-post trends. The intuition: previous posts are taken into
    account but weighted so they do not overpower the current signal.

    Roadmap: replace VADER with fine-tuned BERT classifier from 2025 prototype.
    """
    if not posts:
        return 0.0, []

    raw_scores = []
    for post in posts:
        if _VADER_AVAILABLE:
            scores = _analyzer.polarity_scores(post.text)
            crisis_intensity = (1 - scores["compound"]) / 2
        else:
            # Fallback: keyword-based scoring when VADER not installed
            crisis_intensity = _keyword_sentiment(post.text)
        raw_scores.append(crisis_intensity)
        post.sentiment_score = crisis_intensity

    # Apply EWMA smoothing
    smoothed = _ewma(raw_scores, span=config.EWMA_SPAN)
    return smoothed, raw_scores


def _keyword_sentiment(text: str) -> float:
    """
    Keyword-based crisis intensity fallback when VADER is not installed.
    Install vaderSentiment for production-quality sentiment scoring.
    """
    import re
    text_lower = text.lower()
    crisis_keywords = [
        "hopeless", "worthless", "can't go on", "want to die",
        "end it", "no reason", "kill myself", "exhausted", "depressed",
        "struggling", "dark", "alone", "burden", "painful", "done",
        "can't", "won't", "empty", "numb", "suicid",
    ]
    matches = sum(1 for kw in crisis_keywords if kw in text_lower)
    return min(1.0, matches / 5)


def _ewma(values: List[float], span: int) -> float:
    """
    Exponential Weighted Moving Average.
    Returns the final smoothed value.
    Recent values weighted more heavily; older values fade but aren't forgotten.
    """
    if not values:
        return 0.0
    alpha = 2 / (span + 1)
    result = values[0]
    for v in values[1:]:
        result = alpha * v + (1 - alpha) * result
    return result


# ── VOLUME SPIKE SCORING ──────────────────────────────────────────────────────

def compute_volume_score(n_posts: int,
                          baseline_mean: float,
                          baseline_std: float) -> float:
    """
    Compute volume spike score as a normalized Z-score.

    Z-score measures how many standard deviations the current volume
    is above the 30-day rolling baseline. Capped at VOLUME_ZSCORE_CAP
    to prevent extreme outliers from dominating the score.

    Returns value in [0, 1].
    """
    if baseline_std == 0:
        return 0.5  # no baseline variance — treat as neutral

    z = (n_posts - baseline_mean) / baseline_std
    z = max(-2.0, min(z, config.VOLUME_ZSCORE_CAP))   # clamp to [-2, cap]

    # Normalize from [-2, cap] to [0, 1]
    normalized = (z - (-2.0)) / (config.VOLUME_ZSCORE_CAP - (-2.0))
    return round(normalized, 4)


# ── GEOGRAPHIC CLUSTERING ─────────────────────────────────────────────────────

def compute_geography_score(county_fips: str,
                             neighboring_scores: List[float]) -> float:
    """
    Compute geographic clustering score.

    Full implementation uses Moran's I spatial autocorrelation.
    MVP: uses mean of neighboring county sentiment scores as proxy.

    If neighboring counties show similar distress levels, confidence
    in the signal increases. Absence of geographic clustering does NOT
    invalidate a signal — it just doesn't amplify it.

    Returns value in [0, 1].
    """
    if not neighboring_scores:
        return 0.0   # no neighbor data — neutral, not penalizing

    mean_neighbor_sentiment = statistics.mean(neighboring_scores)
    return round(mean_neighbor_sentiment, 4)


# ── CONFIDENCE ESTIMATION ─────────────────────────────────────────────────────

def compute_confidence(s: float, v: float, g: float,
                        n_posts: int, flags: FlagResult,
                        is_rural: bool) -> ConfidenceEstimate:
    """
    Estimate confidence in the CSS score across three channels.

    Confidence reflects how much the three components agree with each other
    and how much data supports the signal.
    """
    # Agreement between components (standard deviation — lower = more agreement)
    component_std = statistics.stdev([s, v, g]) if len({s, v, g}) > 1 else 0.0
    agreement = max(0.0, 1.0 - component_std * 2)

    # Sample size factor — more posts = more reliable
    threshold = config.MIN_POSTS_RURAL if is_rural else config.MIN_POSTS_URBAN
    sample_factor = min(1.0, n_posts / (threshold * 3))

    # Flag penalty — active flags reduce confidence
    flag_penalty = len(flags.active_flags) * 0.08
    confidence_pct = max(0.1, agreement * sample_factor - flag_penalty)

    # Plain language explanation
    drivers = []
    if s >= config.SENTIMENT_EXTREME_THRESHOLD:
        drivers.append("extreme sentiment")
    elif s >= config.SENTIMENT_MODERATE_MIN:
        drivers.append("moderate sentiment")
    if v >= 0.6:
        drivers.append("significant volume spike")
    if g >= 0.5:
        drivers.append("neighboring county pattern")

    driver_str = ", ".join(drivers) if drivers else "weak signal across components"

    notes = []
    if n_posts < threshold:
        notes.append(f"only {n_posts} posts (minimum {threshold})")
    if flags.active_flags:
        notes.append(f"flags active: {', '.join(flags.active_flags)}")
    if is_rural:
        notes.append("rural county — model may underdetect distress patterns")

    note_str = f" — Caution: {'; '.join(notes)}." if notes else "."
    plain = f"Signal driven by {driver_str}{note_str}"

    # Visual tier
    if confidence_pct >= 0.70:
        visual = "RED" if s >= 0.75 else "AMBER"
    elif confidence_pct >= 0.45:
        visual = "YELLOW"
    else:
        visual = "GRAY"

    return ConfidenceEstimate(
        percentage=round(confidence_pct, 2),
        plain_language=plain,
        visual_tier=visual
    )


# ── ESCALATION CLASSIFICATION ─────────────────────────────────────────────────

def classify_tier(css: float) -> EscalationTier:
    if css >= config.CSS_HIGH_THRESHOLD:
        return EscalationTier.HIGH
    elif css >= config.CSS_MODERATE_THRESHOLD:
        return EscalationTier.MODERATE
    elif css >= config.CSS_LOW_THRESHOLD:
        return EscalationTier.LOW
    else:
        return EscalationTier.NOISE


# ── MAIN SCORING FUNCTION ─────────────────────────────────────────────────────

def evaluate_county(
    posts: List[Post],
    county_fips: str,
    rucc_code: int,
    window_start: datetime,
    baseline_mean: float,
    baseline_std: float,
    neighboring_scores: Optional[List[float]] = None,
    flag_result: Optional[FlagResult] = None,
) -> CSSResult:
    """
    Main entry point: evaluate a county's crisis signal for a 72-hour window.

    Steps:
    1. Sample size gate — route sparse counties to dedicated queue
    2. Compute sentiment score (EWMA-smoothed VADER)
    3. Compute volume spike score
    4. Compute geographic clustering score
    5. Apply conditional weighting logic
    6. Estimate confidence across three channels
    7. Classify escalation tier

    Args:
        posts:              Posts collected in the analysis window
        county_fips:        County FIPS code
        rucc_code:          USDA Rural-Urban Continuum Code
        window_start:       Start of 72-hour analysis window
        baseline_mean:      30-day rolling mean post volume
        baseline_std:       30-day rolling std post volume
        neighboring_scores: Sentiment scores from neighboring counties
        flag_result:        Pre-computed governance flags (or None to skip)

    Returns:
        CSSResult with complete scoring, confidence, and routing information.
    """
    window_end = window_start + timedelta(hours=config.ANALYSIS_WINDOW_HOURS)
    is_rural = rucc_code in config.RURAL_RUCC_CODES
    threshold = config.MIN_POSTS_RURAL if is_rural else config.MIN_POSTS_URBAN
    n_posts = len(posts)

    # Use empty flags if none provided
    if flag_result is None:
        flag_result = FlagResult()

    # ── Step 1: Sample size gate ──────────────────────────────────────────────
    if n_posts < threshold:
        # Route to sparse-data queue — never silence, never treat as urban
        confidence = ConfidenceEstimate(
            percentage=0.20,
            plain_language=(
                f"Insufficient data ({n_posts} posts, minimum {threshold} for "
                f"{'rural' if is_rural else 'urban'} county). "
                f"Routed to sparse-data review queue. "
                f"Apply significant additional judgment."
            ),
            visual_tier="GRAY"
        )
        return CSSResult(
            county_fips=county_fips,
            window_start=window_start,
            window_end=window_end,
            n_posts=n_posts,
            css=0.0,
            escalation_tier=EscalationTier.LOW,   # route to human, not noise
            components=ComponentScores(0, 0, 0, 0),
            flags=flag_result,
            confidence=confidence,
            routed_to_sparse_queue=True,
        )

    # ── Step 2: Sentiment score ───────────────────────────────────────────────
    s_score, _ = compute_sentiment_score(posts)

    # ── Step 3: Volume score ──────────────────────────────────────────────────
    v_score = compute_volume_score(n_posts, baseline_mean, baseline_std)

    # Apply governance flag discount to volume
    v_adjusted = v_score * flag_result.volume_discount

    # ── Step 4: Geographic clustering ────────────────────────────────────────
    g_score = compute_geography_score(
        county_fips, neighboring_scores or []
    )

    # ── Step 5: Conditional CSS weighting ────────────────────────────────────
    if s_score >= config.SENTIMENT_EXTREME_THRESHOLD:
        # Extreme sentiment — anchor is sufficient, no corroboration needed
        css = s_score
    else:
        # Moderate sentiment — corroboration required
        css = (
            config.WEIGHT_SENTIMENT * s_score +
            config.WEIGHT_VOLUME    * v_adjusted +
            config.WEIGHT_GEOGRAPHY * g_score
        )

    css = round(min(1.0, max(0.0, css)), 4)

    # ── Step 6: Confidence estimation ────────────────────────────────────────
    components = ComponentScores(
        sentiment=round(s_score, 4),
        volume=round(v_score, 4),
        geography=round(g_score, 4),
        volume_adjusted=round(v_adjusted, 4),
    )
    confidence = compute_confidence(
        s_score, v_adjusted, g_score, n_posts, flag_result, is_rural
    )

    # ── Step 7: Escalation tier ───────────────────────────────────────────────
    tier = classify_tier(css)

    return CSSResult(
        county_fips=county_fips,
        window_start=window_start,
        window_end=window_end,
        n_posts=n_posts,
        css=css,
        escalation_tier=tier,
        components=components,
        flags=flag_result,
        confidence=confidence,
        routed_to_sparse_queue=False,
    )
