"""Gamma API client for public market discovery (read-only)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from polymarket_paper_bot.config import AppConfig
from polymarket_paper_bot.models import Market, Token
from polymarket_paper_bot.utils import parse_json_list, retry_http, safe_float

logger = logging.getLogger(__name__)


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException | httpx.ConnectError | httpx.RemoteProtocolError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def normalize_market(raw: dict[str, Any]) -> Market | None:
    """
    Normalize a raw Gamma ``market`` object into a :class:`Market`.

    Returns ``None`` when required identifiers are missing — field names and nesting
    can change across API versions, so this must stay defensive.
    """
    market_id = raw.get("id")
    if market_id is None:
        return None
    market_id_str = str(market_id)

    tokens_raw = parse_json_list(raw.get("clobTokenIds"))
    outcomes_raw = parse_json_list(raw.get("outcomes"))
    if not tokens_raw:
        return None

    labels: list[str] = []
    for o in outcomes_raw:
        labels.append(str(o))
    if len(labels) < len(tokens_raw):
        # Pad missing labels — still keep token ids usable for CLOB lookups.
        labels.extend([f"OUTCOME_{i}" for i in range(len(labels), len(tokens_raw))])

    tokens: list[Token] = []
    for idx, tid in enumerate(tokens_raw):
        tid_str = str(tid).strip()
        if not tid_str:
            continue
        label = labels[idx] if idx < len(labels) else f"OUTCOME_{idx}"
        tokens.append(Token(token_id=tid_str, outcome_label=label, market_id=market_id_str))

    if not tokens:
        return None

    vol = safe_float(raw.get("volumeNum"))
    if vol is None:
        vol = safe_float(raw.get("volume"))
    if vol is None:
        vol = 0.0

    vol24 = safe_float(raw.get("volume24hr"))
    if vol24 is None:
        vol24 = safe_float(raw.get("volume24hrClob"))

    liq = safe_float(raw.get("liquidityNum"))
    if liq is None:
        liq = safe_float(raw.get("liquidity"))

    min_sz = safe_float(raw.get("orderMinSize"))
    if min_sz is None:
        min_sz = safe_float(raw.get("order_min_size"))

    enable_ob = raw.get("enableOrderBook")
    if enable_ob is None:
        enable_ob = raw.get("enable_order_book")

    accepting = raw.get("acceptingOrders")
    if accepting is None:
        accepting = raw.get("accepting_orders")

    outcome_prices: list[float] | None = None
    prices_raw = raw.get("outcomePrices")
    parsed_prices = parse_json_list(prices_raw) if prices_raw is not None else []
    if parsed_prices:
        floats: list[float] = []
        for p in parsed_prices:
            pf = safe_float(p)
            if pf is not None:
                floats.append(pf)
        outcome_prices = floats or None

    active = bool(raw.get("active", False))
    closed = bool(raw.get("closed", False))

    question = str(raw.get("question") or raw.get("title") or "")
    slug = str(raw.get("slug") or "")

    return Market(
        market_id=market_id_str,
        question=question,
        slug=slug,
        active=active,
        closed=closed,
        volume=float(vol),
        volume_24hr=float(vol24) if vol24 is not None else None,
        liquidity=float(liq) if liq is not None else None,
        enable_order_book=bool(enable_ob) if enable_ob is not None else None,
        accepting_orders=bool(accepting) if accepting is not None else None,
        min_order_size=float(min_sz) if min_sz is not None else None,
        tokens=tokens,
        outcome_prices=outcome_prices,
        raw=dict(raw),
    )


class GammaClient:
    """Thin Gamma REST client with retries and normalization."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._client = httpx.Client(
            base_url=config.gamma_base_url,
            timeout=httpx.Timeout(config.http_timeout_seconds),
            headers={
                "User-Agent": "polymarket-paper-bot/0.1 (+https://github.com/)",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def get_active_markets(self, limit: int) -> list[Market]:
        """
        Fetch active, unclosed markets ordered by 24h volume (descending).

        The Gamma schema exposes multiple volume fields; we request ordering by
        ``volume24hr`` when supported by the deployment.
        """
        params: dict[str, str | int | bool] = {
            "active": True,
            "closed": False,
            "limit": int(limit),
            "order": "volume24hr",
            "ascending": False,
        }

        def _call() -> list[dict[str, Any]]:
            resp = self._client.get("/markets", params=params)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise ValueError("unexpected Gamma /markets payload (expected list)")
            out: list[dict[str, Any]] = []
            for item in data:
                if isinstance(item, dict):
                    out.append(item)
            return out

        raw_list = retry_http(
            _call,
            max_retries=self._config.http_max_retries,
            is_transient=_is_transient,
            log_warning=logger.warning,
        )

        markets: list[Market] = []
        for raw in raw_list:
            m = normalize_market(raw)
            if m is not None:
                markets.append(m)
        return markets
