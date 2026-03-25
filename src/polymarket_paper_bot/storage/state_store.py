"""JSON persistence for paper-trading state."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from polymarket_paper_bot.config import AppConfig
from polymarket_paper_bot.models import BotState, Position


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_iso(value: str) -> datetime:
    raw = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def position_to_dict(pos: Position) -> dict[str, Any]:
    """Serialize a position for JSON."""
    return {
        "position_id": pos.position_id,
        "market_id": pos.market_id,
        "token_id": pos.token_id,
        "side": pos.side,
        "entry_price": pos.entry_price,
        "size": pos.size,
        "notional": pos.notional,
        "opened_at": _iso(pos.opened_at),
        "entry_reason": pos.entry_reason,
    }


def position_from_dict(data: dict[str, Any]) -> Position:
    """Deserialize a position from JSON-like dict."""
    opened_at_raw = data.get("opened_at")
    if not isinstance(opened_at_raw, str):
        raise ValueError("position.opened_at must be a string")
    return Position(
        position_id=str(data.get("position_id") or ""),
        market_id=str(data.get("market_id") or ""),
        token_id=str(data.get("token_id") or ""),
        side=str(data.get("side") or "YES"),
        entry_price=float(data.get("entry_price") or 0.0),
        size=float(data.get("size") or 0.0),
        notional=float(data.get("notional") or 0.0),
        opened_at=_parse_iso(opened_at_raw),
        entry_reason=str(data.get("entry_reason") or ""),
    )


def bot_state_to_dict(state: BotState) -> dict[str, Any]:
    """Serialize bot state."""
    return {
        "cash_usd": state.cash_usd,
        "realized_pnl_usd": state.realized_pnl_usd,
        "unrealized_pnl_usd": state.unrealized_pnl_usd,
        "open_position": position_to_dict(state.open_position) if state.open_position else None,
        "pending_order": state.pending_order,
        "trades_count": state.trades_count,
        "wins": state.wins,
        "losses": state.losses,
        "total_hold_seconds": state.total_hold_seconds,
        "day_key": state.day_key,
        "day_realized_pnl_usd": state.day_realized_pnl_usd,
        "last_updated": _iso(state.last_updated),
    }


def bot_state_from_dict(data: dict[str, Any]) -> BotState:
    """Deserialize bot state."""
    last_updated_raw = data.get("last_updated")
    if not isinstance(last_updated_raw, str):
        last_updated = datetime.now(timezone.utc)
    else:
        last_updated = _parse_iso(last_updated_raw)

    pos_raw = data.get("open_position")
    pos: Position | None
    if isinstance(pos_raw, dict):
        pos = position_from_dict(pos_raw)
    else:
        pos = None

    pending = data.get("pending_order")
    if pending is not None and not isinstance(pending, dict):
        pending = None

    return BotState(
        cash_usd=float(data.get("cash_usd") or 0.0),
        realized_pnl_usd=float(data.get("realized_pnl_usd") or 0.0),
        unrealized_pnl_usd=float(data.get("unrealized_pnl_usd") or 0.0),
        open_position=pos,
        pending_order=pending,
        trades_count=int(data.get("trades_count") or 0),
        wins=int(data.get("wins") or 0),
        losses=int(data.get("losses") or 0),
        total_hold_seconds=float(data.get("total_hold_seconds") or 0.0),
        day_key=str(data.get("day_key") or ""),
        day_realized_pnl_usd=float(data.get("day_realized_pnl_usd") or 0.0),
        last_updated=last_updated,
    )


class StateStore:
    """Atomic-ish JSON file persistence (write-to-temp + replace)."""

    def __init__(self, config: AppConfig) -> None:
        self._path = (config.data_dir / "bot_state.json").expanduser()

    @property
    def path(self) -> Path:
        """Filesystem path of the state file."""
        return self._path

    def load_or_create(self, config: AppConfig) -> BotState:
        """Load existing state or initialize a fresh paper account."""
        if self._path.exists():
            try:
                raw_text = self._path.read_text(encoding="utf-8")
                payload = json.loads(raw_text)
                if not isinstance(payload, dict):
                    raise ValueError("state file must contain a JSON object")
                return bot_state_from_dict(payload)
            except (OSError, json.JSONDecodeError, ValueError):
                # Corrupt state shouldn't brick the bot; start clean but keep backup path obvious.
                bad = self._path.with_suffix(".json.bad")
                try:
                    self._path.replace(bad)
                except OSError:
                    pass

        now = datetime.now(timezone.utc)
        return BotState(
            cash_usd=float(config.starting_bankroll),
            realized_pnl_usd=0.0,
            unrealized_pnl_usd=0.0,
            open_position=None,
            pending_order=None,
            trades_count=0,
            wins=0,
            losses=0,
            total_hold_seconds=0.0,
            day_key=now.date().isoformat(),
            day_realized_pnl_usd=0.0,
            last_updated=now,
        )

    def save(self, state: BotState) -> None:
        """Persist ``state`` to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        payload = json.dumps(bot_state_to_dict(state), indent=2, sort_keys=True)
        tmp.write_text(payload + "\n", encoding="utf-8")
        tmp.replace(self._path)


def roll_trading_day_if_needed(state: BotState, now: datetime) -> None:
    """Reset per-day counters when the UTC day rolls over."""
    key = now.astimezone(timezone.utc).date().isoformat()
    if state.day_key != key:
        state.day_key = key
        state.day_realized_pnl_usd = 0.0
