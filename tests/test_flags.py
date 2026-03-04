# tests/test_flags.py
"""
Unit tests for the governance flag detection logic.
"""

from datetime import datetime, timedelta

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from ai4mh.flags import (
    Post, detect_bot_activity, detect_media_spike,
    detect_rural_sparse, register_media_event, MEDIA_EVENT_REGISTRY,
    _is_reportative
)


def make_post(post_id, account_id, text, hours_ago=1, county="01073"):
    return Post(
        post_id=post_id,
        account_id=account_id,
        text=text,
        timestamp=datetime.utcnow() - timedelta(hours=hours_ago),
        county_fips=county,
    )


# ── BOT DETECTION TESTS ───────────────────────────────────────────────────────

class TestBotDetection:
    def test_high_velocity_account_flagged(self):
        """Account posting above velocity threshold gets bot_risk flag."""
        posts = [
            make_post(f"p{i}", "bot_account_001",
                      f"I feel hopeless post number {i}", hours_ago=0.1*i)
            for i in range(config.BOT_VELOCITY_THRESHOLD + 2)
        ]
        result = detect_bot_activity(posts)
        assert "bot_risk" in result.active_flags

    def test_normal_account_not_flagged(self):
        """Normal posting behavior does not trigger bot flag."""
        varied_texts = [
            "I am feeling really hopeless and alone tonight.",
            "Things have been dark lately and I need support.",
            "Struggling to get out of bed today. Everything feels heavy.",
            "I reached out to a counselor, hoping it helps.",
            "Trying to take it one day at a time but its hard.",
        ]
        posts = [
            make_post(f"p{i}", f"user_{i:04d}", varied_texts[i], hours_ago=i*3)
            for i in range(5)
        ]
        result = detect_bot_activity(posts)
        assert "bot_risk" not in result.active_flags

    def test_volume_discount_applied_for_bots(self):
        """Bot risk flag reduces volume discount below 1.0."""
        posts = [
            make_post(f"p{i}", "bot_001",
                      f"crisis post {i}", hours_ago=0.05*i)
            for i in range(config.BOT_VELOCITY_THRESHOLD + 3)
        ]
        result = detect_bot_activity(posts)
        if "bot_risk" in result.active_flags and len(
            set(p.account_id for p in posts)
        ) < config.BOT_MIN_UNIQUE_ACCOUNTS:
            assert result.volume_discount < 1.0

    def test_near_duplicate_posts_flagged(self):
        """Highly similar posts within 6 hours are flagged as coordinated."""
        text = "I feel hopeless and want to end it all today"
        posts = [
            make_post(f"p{i}", f"user_{i:04d}", text, hours_ago=0.5)
            for i in range(5)
        ]
        result = detect_bot_activity(posts)
        assert len(result.discounted_posts) > 0


# ── MEDIA SPIKE TESTS ─────────────────────────────────────────────────────────

class TestMediaSpike:
    def test_reportative_posts_trigger_media_flag(self):
        """Posts discussing news (not personal distress) trigger media_context."""
        posts = [
            make_post(f"p{i}", f"user_{i:04d}",
                      "Did you hear about the mental health crisis in the news today?")
            for i in range(10)
        ]
        window_start = datetime.utcnow() - timedelta(hours=72)
        result = detect_media_spike(posts, window_start)
        assert "media_context" in result.active_flags

    def test_firstperson_distress_not_flagged_as_media(self):
        """First-person distress posts are not classified as reportative."""
        posts = [
            make_post(f"p{i}", f"user_{i:04d}",
                      "I can't go on anymore. I feel so hopeless and alone.")
            for i in range(10)
        ]
        window_start = datetime.utcnow() - timedelta(hours=72)
        result = detect_media_spike(posts, window_start)
        assert "media_context" not in result.active_flags


# ── LINGUISTIC REGISTER TESTS ─────────────────────────────────────────────────

class TestLinguisticRegister:
    def test_reportative_patterns_detected(self):
        assert _is_reportative("Did you hear about the suicide case in the news?") is True
        assert _is_reportative("According to reports, mental health crises are rising.") is True
        assert _is_reportative("Breaking news: local mental health crisis reported.") is True

    def test_firstperson_distress_not_reportative(self):
        assert _is_reportative("I can't go on anymore. I feel hopeless.") is False
        assert _is_reportative("I want to end it all. I'm so tired.") is False
        assert _is_reportative("I'm so depressed. Nobody understands me.") is False

    def test_mixed_post_classified_correctly(self):
        # Has reportative marker but also first-person distress → NOT reportative
        text = "Did you hear about the crisis? I feel the same way. I can't go on."
        assert _is_reportative(text) is False


# ── RURAL SPARSE TESTS ────────────────────────────────────────────────────────

class TestRuralSparse:
    def test_rural_below_threshold_flagged(self):
        result = detect_rural_sparse("01085", n_posts=8, rucc_code=8)
        assert "rural_sparse" in result.active_flags
        assert "rural_bias" in result.active_flags

    def test_rural_above_threshold_not_sparse(self):
        result = detect_rural_sparse("01085", n_posts=20, rucc_code=8)
        assert "rural_sparse" not in result.active_flags
        assert "rural_bias" in result.active_flags  # bias flag still present

    def test_urban_below_threshold_flagged(self):
        result = detect_rural_sparse("01073", n_posts=15, rucc_code=2)
        assert "rural_sparse" in result.active_flags
        assert "rural_bias" not in result.active_flags  # not rural

    def test_urban_above_threshold_no_flags(self):
        result = detect_rural_sparse("01073", n_posts=35, rucc_code=2)
        assert not result.active_flags
