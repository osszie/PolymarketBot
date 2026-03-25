"""Tests for risk guardrails."""

from __future__ import annotations

from datetime import datetime, timezone

from polymarket_paper_bot.config import load_config
from polymarket_paper_bot.models import BotState
from polymarket_paper_bot.risk.risk_manager import RiskManager


def _state() -> BotState:
    return BotState(
        cash_usd=10.0,
        realized_pnl_usd=0.0,
        unrealized_pnl_usd=0.0,
        open_position=None,
        pending_order=None,
        trades_count=0,
        wins=0,
        losses=0,
        total_hold_seconds=0.0,
        day_key="2025-01-01",
        day_realized_pnl_usd=0.0,
        last_updated=datetime.now(timezone.utc),
    )


def test_blocks_over_notional() -> None:
    cfg = load_config({"MAX_POSITION_NOTIONAL": "2.0"})
    rm = RiskManager(cfg)
    d = rm.allow_entry(_state(), 5.0, 5.0)
    assert d.allowed is False
    assert d.reason == "exceeds_max_position_notional"


def test_blocks_insufficient_cash() -> None:
    cfg = load_config({"MAX_POSITION_NOTIONAL": "20"})
    s = _state()
    s.cash_usd = 1.0
    rm = RiskManager(cfg)
    d = rm.allow_entry(s, 5.0, 5.0)
    assert d.allowed is False
    assert d.reason == "insufficient_cash"


def test_daily_loss_guard() -> None:
    cfg = load_config({"MAX_POSITION_NOTIONAL": "2.0", "DAILY_MAX_LOSS_USD": "1.0"})
    s = _state()
    s.day_realized_pnl_usd = -1.5
    rm = RiskManager(cfg)
    d = rm.allow_entry(s, 1.0, 5.0)
    assert d.allowed is False
    assert d.reason == "daily_max_loss_breached"


def test_kill_switch() -> None:
    cfg = load_config({"KILL_SWITCH": "true", "MAX_POSITION_NOTIONAL": "10"})
    rm = RiskManager(cfg)
    d = rm.allow_entry(_state(), 1.0, 5.0)
    assert d.allowed is False
    assert d.reason == "kill_switch_enabled"
