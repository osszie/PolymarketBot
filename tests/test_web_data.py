"""Tests for dashboard data loading."""

from __future__ import annotations

from pathlib import Path

from polymarket_paper_bot.web.data import (
    load_bot_state_json,
    load_trades_csv,
    summarize_from_state,
    trades_newest_first,
)


def test_load_trades_missing(tmp_path: Path) -> None:
    assert load_trades_csv(tmp_path / "nope.csv") == []


def test_load_trades_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "trades.csv"
    p.write_text(
        "trade_id,timestamp,market_id,token_id,side,action,price,size,notional,fee,realized_pnl,reason\n"
        "t1,2025-01-01T00:00:00+00:00,m1,tk1,YES,buy,0.5,10,5,0,,paper\n",
        encoding="utf-8",
    )
    rows = load_trades_csv(p)
    assert len(rows) == 1
    assert rows[0]["trade_id"] == "t1"


def test_trades_newest_first_sort(tmp_path: Path) -> None:
    p = tmp_path / "trades.csv"
    p.write_text(
        "trade_id,timestamp,side,action\n"
        "a,2025-01-01T00:00:00+00:00,YES,buy\n"
        "b,2025-01-02T00:00:00+00:00,YES,sell\n",
        encoding="utf-8",
    )
    rows = trades_newest_first(load_trades_csv(p))
    assert rows[0]["trade_id"] == "b"


def test_summarize_none() -> None:
    s = summarize_from_state(None)
    assert s["has_state"] is False


def test_summarize_dict() -> None:
    s = summarize_from_state(
        {
            "cash_usd": 10.0,
            "realized_pnl_usd": 1.0,
            "unrealized_pnl_usd": 0.5,
            "trades_count": 3,
            "wins": 2,
            "losses": 1,
            "day_realized_pnl_usd": 0.25,
            "open_position": None,
        }
    )
    assert s["has_state"] is True
    assert s["cash_usd"] == 10.0


def test_load_state_invalid(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert load_bot_state_json(bad) is None
