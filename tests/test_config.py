"""Tests for environment-driven configuration."""

from __future__ import annotations

from polymarket_paper_bot.config import load_config


def test_defaults() -> None:
    cfg = load_config(
        {
            "DATA_DIR": "/tmp/pm-data-test",
            "LOGS_DIR": "/tmp/pm-logs-test",
        }
    )
    assert cfg.starting_bankroll == 10.0
    assert cfg.max_position_notional == 2.5
    assert cfg.min_market_volume == 10_000.0
    assert cfg.enable_live_adapter is False
    assert cfg.kill_switch is False
    assert str(cfg.data_dir) == "/tmp/pm-data-test"


def test_overrides_numeric() -> None:
    cfg = load_config(
        {
            "STARTING_BANKROLL": "123.5",
            "MIN_SPREAD_CENTS": "5",
            "MAX_MARKETS_TO_SCAN": "12",
            "KILL_SWITCH": "true",
        }
    )
    assert cfg.starting_bankroll == 123.5
    assert cfg.min_spread_cents == 5.0
    assert cfg.max_markets_to_scan == 12
    assert cfg.kill_switch is True
