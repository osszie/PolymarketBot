"""Configurable market filters (Gamma + order book sanity checks)."""

from __future__ import annotations

from polymarket_paper_bot.config import AppConfig
from polymarket_paper_bot.models import Market, OrderBook
from polymarket_paper_bot.strategy.signal_engine import pick_yes_token, spread_cents_from_book


def market_passes_filters(
    market: Market,
    book: OrderBook | None,
    config: AppConfig,
) -> tuple[bool, str]:
    """
    Return whether ``market`` (and optional ``book``) passes baseline filters.

    The book is optional during pure metadata scans; spread/liquidity checks require it.
    """
    if not market.active:
        return False, "inactive"
    if market.closed:
        return False, "closed"

    if market.enable_order_book is not None and not market.enable_order_book:
        return False, "orderbook_disabled"

    if market.accepting_orders is not None and not market.accepting_orders:
        return False, "not_accepting_orders"

    vol = market.volume_24hr if market.volume_24hr is not None else market.volume
    if vol < config.min_market_volume:
        return False, "volume_below_min"

    yes = pick_yes_token(market)
    if yes is None:
        return False, "no_yes_token"

    mid_from_gamma: float | None = None
    if market.outcome_prices and len(market.outcome_prices) >= 1:
        mid_from_gamma = float(market.outcome_prices[0])

    if mid_from_gamma is not None:
        if mid_from_gamma < config.min_price or mid_from_gamma > config.max_price:
            return False, "gamma_mid_out_of_band"

    if book is None:
        return True, "ok_metadata_only"

    if book.token_id != yes.token_id:
        return False, "book_token_mismatch"

    if book.best_bid is None or book.best_ask is None:
        return False, "missing_top_of_book"

    sc = spread_cents_from_book(book)
    if sc is None:
        return False, "missing_spread"

    if sc + 1e-9 < float(config.min_spread_cents):
        return False, "spread_too_tight"

    mid = book.mid
    if mid is None:
        return False, "missing_mid"

    if mid < config.min_price or mid > config.max_price:
        return False, "mid_out_of_band"

    return True, "ok"
