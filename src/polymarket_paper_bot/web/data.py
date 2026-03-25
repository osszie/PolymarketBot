"""Load trades CSV and bot state JSON for the dashboard."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def load_trades_csv(path: Path) -> list[dict[str, str]]:
    """
    Read all rows from ``trades.csv``.

    Returns an empty list if the file is missing or unreadable.
    """
    path = path.expanduser()
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                return []
            return [dict(row) for row in reader]
    except OSError:
        return []


def trades_newest_first(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return trades with most recent timestamp first (best-effort)."""
    if not rows:
        return []

    def key(row: dict[str, str]) -> str:
        return row.get("timestamp") or ""

    return sorted(rows, key=key, reverse=True)


def load_bot_state_json(path: Path) -> dict[str, Any] | None:
    """Load ``bot_state.json`` or return ``None`` if missing/invalid."""
    path = path.expanduser()
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def summarize_from_state(state: dict[str, Any] | None) -> dict[str, Any]:
    """Build display-friendly summary metrics from raw state dict."""
    if state is None:
        return {
            "has_state": False,
            "cash_usd": None,
            "realized_pnl_usd": None,
            "unrealized_pnl_usd": None,
            "trades_count": None,
            "wins": None,
            "losses": None,
            "day_realized_pnl_usd": None,
            "open_position": None,
        }
    pos = state.get("open_position")
    return {
        "has_state": True,
        "cash_usd": state.get("cash_usd"),
        "realized_pnl_usd": state.get("realized_pnl_usd"),
        "unrealized_pnl_usd": state.get("unrealized_pnl_usd"),
        "trades_count": state.get("trades_count"),
        "wins": state.get("wins"),
        "losses": state.get("losses"),
        "day_realized_pnl_usd": state.get("day_realized_pnl_usd"),
        "open_position": pos if isinstance(pos, dict) else None,
    }
