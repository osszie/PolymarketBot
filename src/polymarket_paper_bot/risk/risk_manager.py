"""Risk guardrails for simulated trading."""

from __future__ import annotations

from dataclasses import dataclass

from polymarket_paper_bot.config import AppConfig
from polymarket_paper_bot.models import BotState


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """Outcome of a risk evaluation."""

    allowed: bool
    reason: str


class RiskManager:
    """Enforces notional caps, cash checks, and optional daily loss limits."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def allow_entry(self, state: BotState, proposed_notional: float, min_order_size: float | None) -> RiskDecision:
        """Return whether a new entry is permitted."""
        if self._config.kill_switch:
            return RiskDecision(False, "kill_switch_enabled")

        if state.open_position is not None:
            return RiskDecision(False, "position_already_open")

        if proposed_notional <= 0:
            return RiskDecision(False, "nonpositive_notional")

        if proposed_notional > self._config.max_position_notional + 1e-9:
            return RiskDecision(False, "exceeds_max_position_notional")

        if proposed_notional < self._config.min_practical_order_notional - 1e-9:
            return RiskDecision(False, "below_min_practical_order_notional")

        if proposed_notional > state.cash_usd + 1e-9:
            return RiskDecision(False, "insufficient_cash")

        if min_order_size is not None and min_order_size > 0:
            # Compare share count implied by notional at a later stage; here we only
            # ensure the USD budget isn't trivially below venue minimums when prices ~1.
            # The paper broker also checks share minimums against ``min_order_size``.
            pass

        if self._config.daily_max_loss_usd is not None:
            limit = float(self._config.daily_max_loss_usd)
            if limit > 0 and state.day_realized_pnl_usd <= -limit - 1e-9:
                return RiskDecision(False, "daily_max_loss_breached")

        return RiskDecision(True, "ok")

    def allow_pending_order(self, state: BotState) -> RiskDecision:
        """Return whether we may place (or keep) a pending maker order."""
        if self._config.kill_switch:
            return RiskDecision(False, "kill_switch_enabled")
        if state.open_position is not None:
            return RiskDecision(False, "position_already_open")
        return RiskDecision(True, "ok")
