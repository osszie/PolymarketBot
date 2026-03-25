"""Capture and load JSON snapshots for debugging and replay mode."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from polymarket_paper_bot.clients.clob_client import ClobClient
from polymarket_paper_bot.clients.gamma_client import GammaClient
from polymarket_paper_bot.config import AppConfig
from polymarket_paper_bot.models import Market, OrderBook, OrderBookLevel
from polymarket_paper_bot.strategy.signal_engine import pick_yes_token
from polymarket_paper_bot.utils import safe_float


def order_book_to_dict(book: OrderBook) -> dict[str, Any]:
    """Serialize a normalized order book to JSON-friendly dict."""
    return {
        "token_id": book.token_id,
        "bids": [{"price": b.price, "size": b.size} for b in book.bids],
        "asks": [{"price": a.price, "size": a.size} for a in book.asks],
        "best_bid": book.best_bid,
        "best_ask": book.best_ask,
        "spread": book.spread,
        "spread_cents": book.spread_cents,
        "mid": book.mid,
        "min_order_size": book.min_order_size,
        "tick_size": book.tick_size,
    }


def order_book_from_dict(data: dict[str, Any]) -> OrderBook:
    """Deserialize an order book produced by :func:`order_book_to_dict`."""
    token_id = str(data.get("token_id") or "")
    bids: list[OrderBookLevel] = []
    for lvl in data.get("bids") or []:
        if not isinstance(lvl, dict):
            continue
        p = safe_float(lvl.get("price"))
        s = safe_float(lvl.get("size"))
        if p is None or s is None:
            continue
        bids.append(OrderBookLevel(float(p), float(s)))
    asks: list[OrderBookLevel] = []
    for lvl in data.get("asks") or []:
        if not isinstance(lvl, dict):
            continue
        p = safe_float(lvl.get("price"))
        s = safe_float(lvl.get("size"))
        if p is None or s is None:
            continue
        asks.append(OrderBookLevel(float(p), float(s)))

    return OrderBook(
        token_id=token_id,
        bids=bids,
        asks=asks,
        best_bid=safe_float(data.get("best_bid")),
        best_ask=safe_float(data.get("best_ask")),
        spread=safe_float(data.get("spread")),
        spread_cents=safe_float(data.get("spread_cents")),
        mid=safe_float(data.get("mid")),
        min_order_size=safe_float(data.get("min_order_size")),
        tick_size=safe_float(data.get("tick_size")),
        raw={},
    )


def market_to_dict(market: Market) -> dict[str, Any]:
    """Serialize a normalized market (tokens + scalars)."""
    payload = {
        "market_id": market.market_id,
        "question": market.question,
        "slug": market.slug,
        "active": market.active,
        "closed": market.closed,
        "volume": market.volume,
        "volume_24hr": market.volume_24hr,
        "liquidity": market.liquidity,
        "enable_order_book": market.enable_order_book,
        "accepting_orders": market.accepting_orders,
        "min_order_size": market.min_order_size,
        "outcome_prices": market.outcome_prices,
        "tokens": [
            {"token_id": t.token_id, "outcome_label": t.outcome_label, "market_id": t.market_id}
            for t in market.tokens
        ],
    }
    return payload


def market_from_dict(data: dict[str, Any]) -> Market:
    """Deserialize a market saved by :func:`market_to_dict`."""
    from polymarket_paper_bot.models import Token  # local import to avoid cycles

    tokens_raw = data.get("tokens") or []
    tokens: list[Token] = []
    if isinstance(tokens_raw, list):
        for t in tokens_raw:
            if not isinstance(t, dict):
                continue
            tokens.append(
                Token(
                    token_id=str(t.get("token_id") or ""),
                    outcome_label=str(t.get("outcome_label") or ""),
                    market_id=str(t.get("market_id") or ""),
                )
            )

    op = data.get("outcome_prices")
    outcome_prices: list[float] | None = None
    if isinstance(op, list):
        outcome_prices = [float(x) for x in op]

    v24 = safe_float(data.get("volume_24hr"))
    liq = safe_float(data.get("liquidity"))
    mos = safe_float(data.get("min_order_size"))

    enable_ob = data.get("enable_order_book")
    acc = data.get("accepting_orders")

    return Market(
        market_id=str(data.get("market_id") or ""),
        question=str(data.get("question") or ""),
        slug=str(data.get("slug") or ""),
        active=bool(data.get("active")),
        closed=bool(data.get("closed")),
        volume=float(data.get("volume") or 0.0),
        volume_24hr=float(v24) if v24 is not None else None,
        liquidity=float(liq) if liq is not None else None,
        enable_order_book=bool(enable_ob) if enable_ob is not None else None,
        accepting_orders=bool(acc) if acc is not None else None,
        min_order_size=float(mos) if mos is not None else None,
        tokens=tokens,
        outcome_prices=outcome_prices,
        raw={},
    )


def capture_snapshot_file(
    config: AppConfig,
    *,
    gamma: GammaClient,
    clob: ClobClient,
    out_path: Path,
    markets_limit: int,
) -> Path:
    """
    Fetch markets + YES order books and write a versioned JSON snapshot file.

    This is useful for debugging strategy changes without hammering public APIs.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    markets = gamma.get_active_markets(markets_limit)
    steps: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for m in markets:
        yes = pick_yes_token(m)
        if yes is None:
            continue
        book = clob.get_order_book(yes.token_id)
        if book is None:
            continue
        steps.append(
            {
                "timestamp": now,
                "market": market_to_dict(m),
                "orderbook": order_book_to_dict(book),
            }
        )

    payload = {"version": 1, "created_at": now, "steps": steps}
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


def load_snapshot_file(path: Path) -> list[tuple[Market, OrderBook]]:
    """Load snapshot steps as normalized `(market, order_book)` tuples."""
    raw_text = path.read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise ValueError("snapshot must be a JSON object")
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise ValueError("snapshot.steps must be a list")

    out: list[tuple[Market, OrderBook]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        m_raw = step.get("market")
        b_raw = step.get("orderbook")
        if not isinstance(m_raw, dict) or not isinstance(b_raw, dict):
            continue
        out.append((market_from_dict(m_raw), order_book_from_dict(b_raw)))
    return out
