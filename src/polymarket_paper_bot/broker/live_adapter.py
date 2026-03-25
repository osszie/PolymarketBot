"""
Live trading adapter boundary (disabled by default).

This repository ships **without** a live execution implementation. The public-data
paper bot is the default and only supported execution mode in-tree.

If you implement lawful live trading elsewhere, keep it behind ``ENABLE_LIVE_ADAPTER``
and do not commit secrets. This module exists to make that boundary explicit.
"""

from __future__ import annotations

from typing import Protocol

from polymarket_paper_bot.models import StrategySignal


class LiveTradingAdapter(Protocol):
    """Protocol for a hypothetical authenticated trading backend."""

    def submit_signal(self, signal: StrategySignal) -> None:
        """Submit a live order derived from ``signal``."""
        ...


class DisabledLiveAdapter:
    """Explicit stub that refuses to trade."""

    def submit_signal(self, signal: StrategySignal) -> None:
        raise RuntimeError(
            "Live trading is not implemented in this repository. "
            "Keep default paper mode enabled unless you add a lawful, private adapter."
        )
