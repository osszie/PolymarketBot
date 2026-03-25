"""CLOB public read client (order books, mid, spread)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from polymarket_paper_bot.config import AppConfig
from polymarket_paper_bot.models import OrderBook, OrderBookLevel
from polymarket_paper_bot.utils import retry_http, safe_float

logger = logging.getLogger(__name__)


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException | httpx.ConnectError | httpx.RemoteProtocolError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def _sorted_levels(levels: list[OrderBookLevel], *, side: str) -> list[OrderBookLevel]:
    if side == "bid":
        return sorted(levels, key=lambda x: x.price, reverse=True)
    if side == "ask":
        return sorted(levels, key=lambda x: x.price)
    raise ValueError("side must be bid|ask")


def normalize_orderbook(token_id: str, raw: dict[str, Any]) -> OrderBook | None:
    """
    Normalize a CLOB ``/book`` payload.

    Sorting is applied explicitly because ordering guarantees have differed across docs
    and observed responses — never assume the wire format is already best-first.
    """
    bids_raw = raw.get("bids") or []
    asks_raw = raw.get("asks") or []
    if not isinstance(bids_raw, list) or not isinstance(asks_raw, list):
        return None

    bids: list[OrderBookLevel] = []
    for lvl in bids_raw:
        if not isinstance(lvl, dict):
            continue
        p = safe_float(lvl.get("price"))
        s = safe_float(lvl.get("size"))
        if p is None or s is None:
            continue
        bids.append(OrderBookLevel(price=float(p), size=float(s)))

    asks: list[OrderBookLevel] = []
    for lvl in asks_raw:
        if not isinstance(lvl, dict):
            continue
        p = safe_float(lvl.get("price"))
        s = safe_float(lvl.get("size"))
        if p is None or s is None:
            continue
        asks.append(OrderBookLevel(price=float(p), size=float(s)))

    bids = _sorted_levels(bids, side="bid")
    asks = _sorted_levels(asks, side="ask")

    best_bid = bids[0].price if bids else None
    best_ask = asks[0].price if asks else None

    spread: float | None = None
    spread_cents: float | None = None
    mid: float | None = None
    if best_bid is not None and best_ask is not None and best_ask >= best_bid:
        spread = float(best_ask - best_bid)
        spread_cents = spread * 100.0
        mid = float((best_bid + best_ask) / 2.0)

    min_order = safe_float(raw.get("min_order_size"))
    tick = safe_float(raw.get("tick_size"))

    return OrderBook(
        token_id=token_id,
        bids=bids,
        asks=asks,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        spread_cents=spread_cents,
        mid=mid,
        min_order_size=float(min_order) if min_order is not None else None,
        tick_size=float(tick) if tick is not None else None,
        raw=dict(raw),
    )


class ClobClient:
    """Public CLOB REST reader."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._client = httpx.Client(
            base_url=config.clob_base_url,
            timeout=httpx.Timeout(config.http_timeout_seconds),
            headers={
                "User-Agent": "polymarket-paper-bot/0.1 (+https://github.com/)",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def get_order_book(self, token_id: str) -> OrderBook | None:
        """Fetch and normalize the order book for ``token_id``."""

        def _call() -> OrderBook | None:
            resp = self._client.get("/book", params={"token_id": token_id})
            if resp.status_code in (404, 400, 422):
                return None
            # Some deployments return JSON errors as 200 with {"error": "..."}; handle both.
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict):
                return None
            if payload.get("error"):
                return None
            return normalize_orderbook(token_id, payload)

        return retry_http(
            _call,
            max_retries=self._config.http_max_retries,
            is_transient=_is_transient,
            log_warning=logger.warning,
        )

    def get_midpoint(self, token_id: str) -> float | None:
        """Return midpoint price from ``/midpoint`` when available."""

        def _call() -> float | None:
            resp = self._client.get("/midpoint", params={"token_id": token_id})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict):
                return None
            mid = safe_float(payload.get("mid"))
            return float(mid) if mid is not None else None

        try:
            return retry_http(
                _call,
                max_retries=self._config.http_max_retries,
                is_transient=_is_transient,
                log_warning=logger.warning,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    def get_spread(self, token_id: str) -> float | None:
        """Return absolute spread from ``/spread`` when available (price units, not cents)."""

        def _call() -> float | None:
            resp = self._client.get("/spread", params={"token_id": token_id})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict):
                return None
            sp = safe_float(payload.get("spread"))
            return float(sp) if sp is not None else None

        try:
            return retry_http(
                _call,
                max_retries=self._config.http_max_retries,
                is_transient=_is_transient,
                log_warning=logger.warning,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
