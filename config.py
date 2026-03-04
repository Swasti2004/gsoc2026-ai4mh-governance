# config.py
# ─────────────────────────────────────────────────────────────────────────────
# Central configuration for AI4MH Governance Layer.
#
# WHY THIS FILE EXISTS:
# Every threshold in a public health system is a policy decision, not just
# a technical one. Keeping all thresholds here means:
#   - Changes are visible, deliberate, and reviewable
#   - No magic numbers buried in code
#   - Threshold adjustments don't require touching core logic
# ─────────────────────────────────────────────────────────────────────────────

# ── SAMPLE SIZE THRESHOLDS ────────────────────────────────────────────────────
# Urban counties need 30 posts to produce a reliable signal.
# Rural counties (RUCC codes 7-9) use 15 — not because they matter less,
# but because structural lower social media activity is not lower crisis risk.
MIN_POSTS_URBAN = 30
MIN_POSTS_RURAL = 15

# RUCC codes considered rural (USDA Rural-Urban Continuum Codes)
RURAL_RUCC_CODES = [7, 8, 9]

# ── CSS ESCALATION THRESHOLDS ─────────────────────────────────────────────────
# These determine which tier a computed CSS score maps to.
# Changing these values changes the system's sensitivity — do so deliberately.
CSS_HIGH_THRESHOLD     = 0.75   # Immediate escalation to senior analyst
CSS_MODERATE_THRESHOLD = 0.50   # On-call analyst within 4 hours
CSS_LOW_THRESHOLD      = 0.30   # Daily review queue
# Below CSS_LOW_THRESHOLD → NOISE, archived only

# ── SENTIMENT THRESHOLDS ──────────────────────────────────────────────────────
# If BERT/VADER risk score exceeds this, sentiment alone is sufficient signal.
# Below this, volume and geography must corroborate.
SENTIMENT_EXTREME_THRESHOLD = 0.85
SENTIMENT_MODERATE_MIN      = 0.45

# ── CSS COMPONENT WEIGHTS (moderate sentiment path) ───────────────────────────
# These weights apply when sentiment is moderate (not extreme).
# Sentiment anchors; volume and geography modify confidence.
WEIGHT_SENTIMENT   = 0.45
WEIGHT_VOLUME      = 0.35
WEIGHT_GEOGRAPHY   = 0.20

# Discount multiplier applied to volume when bot or media flag is active.
# 0.5 = volume contribution halved when signal is suspected unreliable.
VOLUME_DISCOUNT_MULTIPLIER = 0.50

# ── VOLUME SPIKE DETECTION ────────────────────────────────────────────────────
# How many days of history to use for rolling baseline
VOLUME_BASELINE_DAYS = 30

# Z-score cap — prevents extreme outliers from dominating the score
VOLUME_ZSCORE_CAP = 4.0

# ── EWMA SMOOTHING ────────────────────────────────────────────────────────────
# Span for Exponential Weighted Moving Average.
# Higher span = more weight on historical data, slower to react.
# Lower span = more reactive, more noise.
# 7 days balances weekend/holiday noise against genuine trend detection.
EWMA_SPAN = 7

# ── BOT DETECTION ─────────────────────────────────────────────────────────────
# Maximum posts per account per 24-hour window before flagging as suspicious
BOT_VELOCITY_THRESHOLD = 10

# Cosine similarity threshold for near-duplicate detection
BOT_COSINE_SIMILARITY_THRESHOLD = 0.92

# If volume Z-score exceeds this but unique accounts are below BOT_MIN_UNIQUE_ACCOUNTS,
# attach bot_risk flag
BOT_ZSCORE_TRIGGER      = 3.0
BOT_MIN_UNIQUE_ACCOUNTS = 20

# ── MEDIA SPIKE DETECTION ─────────────────────────────────────────────────────
# Hours before/after a registered media event to consider a spike media-driven
MEDIA_EVENT_WINDOW_HOURS = 48

# Linguistic register: posts classified as reportative receive this weight
MEDIA_REPORTATIVE_WEIGHT = 0.60

# ── GEOGRAPHIC CLUSTERING ─────────────────────────────────────────────────────
# Moran's I threshold above which geographic clustering is considered significant
# (Currently mocked in MVP — full implementation in roadmap)
MORANS_I_THRESHOLD = 0.30

# ── AUDIT LOG ─────────────────────────────────────────────────────────────────
AUDIT_LOG_PATH = "audit_log.jsonl"   # append-only JSON Lines file
AUDIT_RETENTION_YEARS = 7            # public health data governance standard

# ── TIME WINDOW ───────────────────────────────────────────────────────────────
ANALYSIS_WINDOW_HOURS = 72           # 72-hour rolling window per the brief
