# ai4mh/audit.py
# ─────────────────────────────────────────────────────────────────────────────
# Audit Logging — Immutable Record of Every System Decision
#
# Every CSS computation generates an audit record.
# Records are append-only (never modified, never deleted).
# Four categories per record:
#   1. What the system SAW (signal data, sample size, flags)
#   2. What the system DECIDED (CSS score, escalation tier)
#   3. What the HUMAN DID (confirmed, dismissed, deferred + rationale)
#   4. What HAPPENED AFTER (outcome — populated 30 days post-event)
#
# WHY THIS MATTERS:
# Audit logging transforms monitoring into accountability.
# If something goes wrong — a missed crisis, a false alarm — you can
# reconstruct exactly what happened and why.
# Analyst overrides and confirmed outcomes feed back into threshold
# calibration, closing the improvement loop.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

import config
from ai4mh.scoring import CSSResult, EscalationTier


# ── ANALYST ACTIONS ───────────────────────────────────────────────────────────

class AnalystAction(str, Enum):
    CONFIRMED = "CONFIRMED"   # Signal confirmed as genuine — action taken
    DISMISSED = "DISMISSED"   # Signal dismissed — no action warranted
    DEFERRED  = "DEFERRED"    # Needs more information — decision pending


# ── AUDIT RECORD ──────────────────────────────────────────────────────────────

@dataclass
class AuditRecord:
    """
    Immutable audit record for a single CSS evaluation event.

    Fields are grouped into four categories matching our governance design:
    signal inputs, system decision, human review, and outcome.
    """
    # ── Identification ────────────────────────────────────────────────────────
    event_id: str                   # UUID — unique per computation
    timestamp_utc: str              # ISO-8601 when evaluation ran

    # ── Category 1: What the system SAW ──────────────────────────────────────
    county_fips: str
    window_start: str               # ISO-8601
    window_end: str                 # ISO-8601
    n_posts: int
    sentiment_score: float
    volume_score: float
    volume_adjusted: float          # after flag-based discount
    geography_score: float
    active_flags: List[str]
    flag_notes: List[str]
    routed_to_sparse_queue: bool

    # ── Category 2: What the system DECIDED ──────────────────────────────────
    css: float
    escalation_tier: str            # EscalationTier value
    confidence_pct: float
    confidence_plain_language: str
    confidence_visual_tier: str

    # ── Category 3: What the HUMAN DID ───────────────────────────────────────
    # Populated when analyst reviews the signal
    analyst_id: Optional[str] = None
    analyst_action: Optional[str] = None    # AnalystAction value
    analyst_rationale: Optional[str] = None
    analyst_review_timestamp: Optional[str] = None

    # ── Category 4: What HAPPENED AFTER ──────────────────────────────────────
    # Populated 30 days post-event — enables feedback loop
    outcome_confirmed: Optional[bool] = None
    intervention_deployed: Optional[bool] = None
    outcome_notes: Optional[str] = None
    outcome_logged_timestamp: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ── AUDIT LOGGER ─────────────────────────────────────────────────────────────

class AuditLogger:
    """
    Append-only audit log writer.

    Uses JSON Lines format (.jsonl) — one record per line.
    This format is:
    - Easy to append without loading the full file
    - Easy to query with standard tools (jq, pandas, etc.)
    - Easy to ingest into a tamper-evident log store (AWS QLDB, etc.)
    """

    def __init__(self, log_path: Optional[str] = None):
        self.log_path = Path(log_path or config.AUDIT_LOG_PATH)

    def log_evaluation(self, result: CSSResult) -> AuditRecord:
        """
        Create and persist an audit record from a CSSResult.
        Returns the created record.
        """
        record = AuditRecord(
            event_id=str(uuid.uuid4()),
            timestamp_utc=datetime.utcnow().isoformat() + "Z",
            county_fips=result.county_fips,
            window_start=result.window_start.isoformat(),
            window_end=result.window_end.isoformat(),
            n_posts=result.n_posts,
            sentiment_score=result.components.sentiment,
            volume_score=result.components.volume,
            volume_adjusted=result.components.volume_adjusted,
            geography_score=result.components.geography,
            active_flags=result.flags.active_flags,
            flag_notes=result.flags.plain_language_notes,
            routed_to_sparse_queue=result.routed_to_sparse_queue,
            css=result.css,
            escalation_tier=result.escalation_tier.value,
            confidence_pct=result.confidence.percentage,
            confidence_plain_language=result.confidence.plain_language,
            confidence_visual_tier=result.confidence.visual_tier,
        )
        self._append(record)
        return record

    def log_analyst_review(self, event_id: str, analyst_id: str,
                            action: AnalystAction,
                            rationale: str) -> bool:
        """
        Record an analyst's review decision for a given event.

        In production this would update the record in a database.
        In MVP: appends a review record referencing the original event_id.
        Returns True if successful.
        """
        review_record = {
            "record_type": "analyst_review",
            "event_id": event_id,
            "analyst_id": analyst_id,
            "analyst_action": action.value,
            "analyst_rationale": rationale,
            "analyst_review_timestamp": datetime.utcnow().isoformat() + "Z",
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(review_record) + "\n")
            return True
        except Exception as e:
            print(f"[AUDIT ERROR] Failed to log analyst review: {e}")
            return False

    def log_outcome(self, event_id: str, outcome_confirmed: bool,
                    intervention_deployed: bool,
                    notes: str = "") -> bool:
        """
        Record the real-world outcome of a flagged signal.
        Called 30 days post-event as part of the feedback loop.
        """
        outcome_record = {
            "record_type": "outcome",
            "event_id": event_id,
            "outcome_confirmed": outcome_confirmed,
            "intervention_deployed": intervention_deployed,
            "outcome_notes": notes,
            "outcome_logged_timestamp": datetime.utcnow().isoformat() + "Z",
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(outcome_record) + "\n")
            return True
        except Exception as e:
            print(f"[AUDIT ERROR] Failed to log outcome: {e}")
            return False

    def get_all_records(self) -> List[dict]:
        """Read all records from the audit log."""
        if not self.log_path.exists():
            return []
        records = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records

    def _append(self, record: AuditRecord) -> None:
        """Append a single record to the log file."""
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except Exception as e:
            print(f"[AUDIT ERROR] Failed to write audit record: {e}")
