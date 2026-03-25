"""Candidate scoring and selection (prefers liquidity + wider spreads)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from polymarket_paper_bot.config import AppConfig
from polymarket_paper_bot.models import Market, OrderBook
from polymarket_paper_bot.strategy.filters import market_passes_filters
from polymarket_paper_bot.strategy.signal_engine import pick_yes_token, spread_cents_from_book


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    """A market/order book pair with a scalar ranking score."""

    market: Market
    book: OrderBook
    score: float


def score_candidate(market: Market, book: OrderBook, config: AppConfig) -> float | None:
    """
    Compute a higher-is-better score.

    Heuristic: prioritize 24h volume (liquidity proxy) and wider spreads, with mild
    regularization to avoid exploding scores when volume is huge.
    """
    ok, _reason = market_passes_filters(market, book, config)
    if not ok:
        return None

    yes = pick_yes_token(market)
    if yes is None or yes.token_id != book.token_id:
        return None

    vol = market.volume_24hr if market.volume_24hr is not None else market.volume
    sc = spread_cents_from_book(book)
    if sc is None:
        return None

    # log1p dampens dominance of extremely large markets while still rewarding depth
    liq_term = math.log1p(max(vol, 0.0))
    spread_term = max(sc, 0.0)
    return 1.0 * liq_term + 0.35 * spread_term


def rank_and_select(
    items: list[tuple[Market, OrderBook]],
    config: AppConfig,
    top_n: int,
) -> list[ScoredCandidate]:
    """Filter, score, sort descending, and return the top ``top_n`` candidates."""
    scored: list[ScoredCandidate] = []
    for m, b in items:
        s = score_candidate(m, b, config)
        if s is None:
            continue
        scored.append(ScoredCandidate(market=m, book=b, score=float(s)))

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[: max(0, int(top_n))]
