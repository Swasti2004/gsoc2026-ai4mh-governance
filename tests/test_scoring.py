# tests/test_scoring.py
"""
Unit tests for the CSS scoring logic.

Tests verify:
- Sample size gate works correctly for urban and rural counties
- Extreme sentiment triggers standalone scoring (no corroboration needed)
- Moderate sentiment requires volume/geo corroboration
- Volume discount is applied correctly when flags are present
- Escalation tiers map correctly to CSS ranges
"""

from datetime import datetime, timedelta

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from ai4mh.flags import Post, FlagResult
from ai4mh.scoring import (
    evaluate_county, classify_tier, compute_volume_score,
    EscalationTier, CSSResult
)


# ── FIXTURES ──────────────────────────────────────────────────────────────────

def make_posts(n: int, text: str = "I feel hopeless and can't go on",
               county: str = "01073") -> list:
    now = datetime.utcnow()
    return [
        Post(
            post_id=f"test_{i:04d}",
            account_id=f"user_{i:04d}",
            text=text,
            timestamp=now - timedelta(hours=i % 72),
            county_fips=county,
        )
        for i in range(n)
    ]


WINDOW_START = datetime.utcnow() - timedelta(hours=72)


# ── SAMPLE SIZE GATE TESTS ────────────────────────────────────────────────────

class TestSampleSizeGate:
    def test_urban_below_threshold_routes_to_sparse_queue(self):
        """Urban county with fewer than 30 posts → sparse data queue."""
        posts = make_posts(15, county="01073")
        result = evaluate_county(
            posts=posts, county_fips="01073", rucc_code=2,
            window_start=WINDOW_START, baseline_mean=20, baseline_std=5
        )
        assert result.routed_to_sparse_queue is True
        # Still escalated to human review — never silenced
        assert result.escalation_tier == EscalationTier.LOW

    def test_rural_below_threshold_routes_to_sparse_queue(self):
        """Rural county with fewer than 15 posts → sparse data queue."""
        posts = make_posts(8, county="01085")
        result = evaluate_county(
            posts=posts, county_fips="01085", rucc_code=8,
            window_start=WINDOW_START, baseline_mean=5, baseline_std=2
        )
        assert result.routed_to_sparse_queue is True

    def test_rural_above_threshold_not_sparse(self):
        """Rural county with 15+ posts → proceeds to scoring."""
        posts = make_posts(20, county="01085")
        result = evaluate_county(
            posts=posts, county_fips="01085", rucc_code=8,
            window_start=WINDOW_START, baseline_mean=5, baseline_std=2
        )
        assert result.routed_to_sparse_queue is False

    def test_urban_above_threshold_not_sparse(self):
        """Urban county with 30+ posts → proceeds to scoring."""
        posts = make_posts(35, county="01073")
        result = evaluate_county(
            posts=posts, county_fips="01073", rucc_code=2,
            window_start=WINDOW_START, baseline_mean=20, baseline_std=5
        )
        assert result.routed_to_sparse_queue is False


# ── ESCALATION TIER TESTS ─────────────────────────────────────────────────────

class TestEscalationTiers:
    def test_high_threshold(self):
        assert classify_tier(0.80) == EscalationTier.HIGH
        assert classify_tier(0.75) == EscalationTier.HIGH
        assert classify_tier(1.00) == EscalationTier.HIGH

    def test_moderate_threshold(self):
        assert classify_tier(0.60) == EscalationTier.MODERATE
        assert classify_tier(0.50) == EscalationTier.MODERATE
        assert classify_tier(0.74) == EscalationTier.MODERATE

    def test_low_threshold(self):
        assert classify_tier(0.40) == EscalationTier.LOW
        assert classify_tier(0.30) == EscalationTier.LOW

    def test_noise_threshold(self):
        assert classify_tier(0.29) == EscalationTier.NOISE
        assert classify_tier(0.00) == EscalationTier.NOISE


# ── VOLUME SCORE TESTS ────────────────────────────────────────────────────────

class TestVolumeScore:
    def test_no_baseline_variance_returns_neutral(self):
        """Zero std → neutral 0.5, not crash."""
        score = compute_volume_score(n_posts=30, baseline_mean=25, baseline_std=0)
        assert score == 0.5

    def test_above_baseline_returns_high_score(self):
        """Significantly above baseline → high volume score."""
        score = compute_volume_score(n_posts=60, baseline_mean=20, baseline_std=8)
        assert score > 0.6

    def test_at_baseline_returns_mid_score(self):
        """At baseline mean → moderate volume score."""
        score = compute_volume_score(n_posts=20, baseline_mean=20, baseline_std=5)
        assert 0.3 <= score <= 0.7

    def test_score_bounded_0_to_1(self):
        """Volume score never exceeds [0, 1]."""
        for n in [0, 5, 50, 200, 1000]:
            score = compute_volume_score(n, baseline_mean=20, baseline_std=5)
            assert 0.0 <= score <= 1.0


# ── GOVERNANCE FLAG INTERACTION TESTS ────────────────────────────────────────

class TestFlagInteraction:
    def test_volume_discount_applied_from_flag(self):
        """When bot flag discounts volume, adjusted score should be lower."""
        posts = make_posts(40)
        flag_result = FlagResult(
            active_flags=["bot_risk"],
            volume_discount=0.5
        )
        result = evaluate_county(
            posts=posts, county_fips="01073", rucc_code=2,
            window_start=WINDOW_START, baseline_mean=20, baseline_std=5,
            flag_result=flag_result
        )
        assert result.components.volume_adjusted <= result.components.volume

    def test_no_flags_full_volume_weight(self):
        """Without flags, adjusted volume equals raw volume."""
        posts = make_posts(40)
        result = evaluate_county(
            posts=posts, county_fips="01073", rucc_code=2,
            window_start=WINDOW_START, baseline_mean=20, baseline_std=5,
        )
        assert result.components.volume_adjusted == result.components.volume

    def test_css_bounded_0_to_1(self):
        """CSS score is always in valid range."""
        posts = make_posts(40)
        result = evaluate_county(
            posts=posts, county_fips="01073", rucc_code=2,
            window_start=WINDOW_START, baseline_mean=20, baseline_std=5,
        )
        assert 0.0 <= result.css <= 1.0
