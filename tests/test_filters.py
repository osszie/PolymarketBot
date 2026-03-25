"""Tests for market filtering and candidate scoring."""

from __future__ import annotations

from polymarket_paper_bot.config import load_config
from polymarket_paper_bot.models import Market, OrderBook, OrderBookLevel, Token
from polymarket_paper_bot.strategy.filters import market_passes_filters
from polymarket_paper_bot.strategy.market_selector import rank_and_select, score_candidate


def _mk_market(**kwargs: object) -> Market:
    defaults = {
        "market_id": "m1",
        "question": "q",
        "slug": "s",
        "active": True,
        "closed": False,
        "volume": 50_000.0,
        "volume_24hr": 50_000.0,
        "liquidity": 1.0,
        "enable_order_book": True,
        "accepting_orders": True,
        "min_order_size": 5.0,
        "tokens": [Token(token_id="yes1", outcome_label="Yes", market_id="m1")],
        "outcome_prices": [0.45],
        "raw": {},
    }
    defaults.update(kwargs)
    return Market(**defaults)  # type: ignore[arg-type]


def _mk_book() -> OrderBook:
    bids = [OrderBookLevel(0.44, 100.0), OrderBookLevel(0.43, 50.0)]
    asks = [OrderBookLevel(0.48, 100.0), OrderBookLevel(0.49, 50.0)]
    return OrderBook(
        token_id="yes1",
        bids=bids,
        asks=asks,
        best_bid=0.44,
        best_ask=0.48,
        spread=0.04,
        spread_cents=4.0,
        mid=0.46,
        min_order_size=5.0,
        tick_size=0.01,
        raw={},
    )


def test_market_passes_filters_ok() -> None:
    cfg = load_config({"MIN_SPREAD_CENTS": "3", "MIN_MARKET_VOLUME": "10000", "MIN_PRICE": "0.10", "MAX_PRICE": "0.90"})
    m = _mk_market()
    b = _mk_book()
    ok, reason = market_passes_filters(m, b, cfg)
    assert ok is True
    assert reason == "ok"


def test_market_fails_volume() -> None:
    cfg = load_config({"MIN_MARKET_VOLUME": "999999999"})
    m = _mk_market(volume=100.0, volume_24hr=100.0)
    b = _mk_book()
    ok, reason = market_passes_filters(m, b, cfg)
    assert ok is False
    assert reason == "volume_below_min"


def test_scoring_prefers_wider_spread_and_volume() -> None:
    cfg = load_config({"MIN_SPREAD_CENTS": "1", "MIN_MARKET_VOLUME": "1"})
    m1 = _mk_market(market_id="a", volume_24hr=1_000_000.0)
    m2 = _mk_market(market_id="b", volume_24hr=1_000.0)
    b1 = _mk_book()
    b2 = _mk_book()
    b2.bids = [OrderBookLevel(0.40, 10.0)]
    b2.asks = [OrderBookLevel(0.50, 10.0)]
    b2.best_bid = 0.40
    b2.best_ask = 0.50
    b2.spread = 0.10
    b2.spread_cents = 10.0
    b2.mid = 0.45
    s1 = score_candidate(m1, b1, cfg)
    s2 = score_candidate(m2, b2, cfg)
    assert s1 is not None and s2 is not None
    assert s1 > s2  # higher liquidity dominates even with tighter spread in this fixture

    ranked = rank_and_select([(m1, b1), (m2, b2)], cfg, top_n=2)
    assert ranked[0].market.market_id == "a"


def test_rank_select_top_n() -> None:
    cfg = load_config({"MIN_SPREAD_CENTS": "1", "MIN_MARKET_VOLUME": "1"})
    items = []
    for i in range(5):
        m = _mk_market(market_id=str(i), volume_24hr=float(1000 * (i + 1)))
        b = _mk_book()
        items.append((m, b))
    ranked = rank_and_select(items, cfg, top_n=2)
    assert len(ranked) == 2
