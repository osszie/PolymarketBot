"""Application configuration loaded from environment variables with defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


def _m_float(m: Mapping[str, str], key: str, default: float) -> float:
    raw = m.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    return float(raw)


def _m_int(m: Mapping[str, str], key: str, default: int) -> int:
    raw = m.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    return int(raw)


def _m_bool(m: Mapping[str, str], key: str, default: bool) -> bool:
    raw = m.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _m_str(m: Mapping[str, str], key: str, default: str) -> str:
    raw = m.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw)


def _m_optional_float(m: Mapping[str, str], key: str) -> float | None:
    raw = m.get(key)
    if raw is None or str(raw).strip() == "":
        return None
    return float(raw)


def _m_optional_int(m: Mapping[str, str], key: str) -> int | None:
    raw = m.get(key)
    if raw is None or str(raw).strip() == "":
        return None
    return int(raw)


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Runtime configuration for the paper bot."""

    starting_bankroll: float
    max_position_notional: float
    min_market_volume: float
    min_spread_cents: float
    take_profit_cents: float
    stop_loss_cents: float
    max_hold_minutes: float
    loop_seconds: float
    max_markets_to_scan: int
    min_price: float
    max_price: float
    paper_fill_probability: float
    min_practical_order_notional: float
    daily_max_loss_usd: float | None
    kill_switch: bool
    enable_live_adapter: bool
    log_level: str
    data_dir: Path
    logs_dir: Path
    gamma_base_url: str
    clob_base_url: str
    http_timeout_seconds: float
    http_max_retries: int
    random_seed: int | None

    def ensure_runtime_dirs(self) -> None:
        """Create data and log directories if missing."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


def load_config(overrides: Mapping[str, str] | None = None) -> AppConfig:
    """
    Load configuration from the process environment.

    When ``overrides`` is provided (mainly for tests), values override ``os.environ``.
    """
    merged: dict[str, str] = {k: str(v) for k, v in os.environ.items()}
    if overrides:
        merged.update({k: str(v) for k, v in overrides.items()})
    return _load_config_from_mapping(merged)


def _load_config_from_mapping(m: Mapping[str, str]) -> AppConfig:
    data_dir = Path(_m_str(m, "DATA_DIR", "./data")).expanduser()
    logs_dir = Path(_m_str(m, "LOGS_DIR", "./logs")).expanduser()
    return AppConfig(
        starting_bankroll=_m_float(m, "STARTING_BANKROLL", 10.0),
        max_position_notional=_m_float(m, "MAX_POSITION_NOTIONAL", 2.5),
        min_market_volume=_m_float(m, "MIN_MARKET_VOLUME", 10_000.0),
        min_spread_cents=_m_float(m, "MIN_SPREAD_CENTS", 3.0),
        take_profit_cents=_m_float(m, "TAKE_PROFIT_CENTS", 2.0),
        stop_loss_cents=_m_float(m, "STOP_LOSS_CENTS", 3.0),
        max_hold_minutes=_m_float(m, "MAX_HOLD_MINUTES", 120.0),
        loop_seconds=_m_float(m, "LOOP_SECONDS", 10.0),
        max_markets_to_scan=_m_int(m, "MAX_MARKETS_TO_SCAN", 50),
        min_price=_m_float(m, "MIN_PRICE", 0.10),
        max_price=_m_float(m, "MAX_PRICE", 0.90),
        paper_fill_probability=_m_float(m, "PAPER_FILL_PROBABILITY", 0.25),
        min_practical_order_notional=_m_float(m, "MIN_PRACTICAL_ORDER_NOTIONAL", 0.50),
        daily_max_loss_usd=_m_optional_float(m, "DAILY_MAX_LOSS_USD"),
        kill_switch=_m_bool(m, "KILL_SWITCH", False),
        enable_live_adapter=_m_bool(m, "ENABLE_LIVE_ADAPTER", False),
        log_level=_m_str(m, "LOG_LEVEL", "INFO").upper(),
        data_dir=data_dir,
        logs_dir=logs_dir,
        gamma_base_url=_m_str(m, "GAMMA_BASE_URL", "https://gamma-api.polymarket.com").rstrip("/"),
        clob_base_url=_m_str(m, "CLOB_BASE_URL", "https://clob.polymarket.com").rstrip("/"),
        http_timeout_seconds=_m_float(m, "HTTP_TIMEOUT_SECONDS", 15.0),
        http_max_retries=_m_int(m, "HTTP_MAX_RETRIES", 4),
        random_seed=_m_optional_int(m, "RANDOM_SEED"),
    )


def config_to_log_dict(config: AppConfig) -> dict[str, Any]:
    """Return a dict safe for logging (paths as strings)."""
    return {
        "starting_bankroll": config.starting_bankroll,
        "max_position_notional": config.max_position_notional,
        "min_market_volume": config.min_market_volume,
        "min_spread_cents": config.min_spread_cents,
        "take_profit_cents": config.take_profit_cents,
        "stop_loss_cents": config.stop_loss_cents,
        "max_hold_minutes": config.max_hold_minutes,
        "loop_seconds": config.loop_seconds,
        "max_markets_to_scan": config.max_markets_to_scan,
        "min_price": config.min_price,
        "max_price": config.max_price,
        "paper_fill_probability": config.paper_fill_probability,
        "min_practical_order_notional": config.min_practical_order_notional,
        "daily_max_loss_usd": config.daily_max_loss_usd,
        "kill_switch": config.kill_switch,
        "enable_live_adapter": config.enable_live_adapter,
        "data_dir": str(config.data_dir),
        "logs_dir": str(config.logs_dir),
        "gamma_base_url": config.gamma_base_url,
        "clob_base_url": config.clob_base_url,
        "http_timeout_seconds": config.http_timeout_seconds,
        "http_max_retries": config.http_max_retries,
        "random_seed": config.random_seed,
    }
