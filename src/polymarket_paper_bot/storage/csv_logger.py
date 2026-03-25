"""CSV append-only trade logging."""

from __future__ import annotations

import csv
from pathlib import Path

from polymarket_paper_bot.config import AppConfig
from polymarket_paper_bot.models import Trade


class CsvTradeLogger:
    """Append trades to a CSV file (creates header on first write)."""

    HEADERS = [
        "trade_id",
        "timestamp",
        "market_id",
        "token_id",
        "side",
        "action",
        "price",
        "size",
        "notional",
        "fee",
        "realized_pnl",
        "reason",
    ]

    def __init__(self, config: AppConfig) -> None:
        self._path = (config.data_dir / "trades.csv").expanduser()

    @property
    def path(self) -> Path:
        """Filesystem path of the CSV file."""
        return self._path

    def append(self, trade: Trade) -> None:
        """Append a single trade row."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self._path.exists()
        with self._path.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=self.HEADERS)
            if new_file:
                w.writeheader()
            w.writerow(
                {
                    "trade_id": trade.trade_id,
                    "timestamp": trade.timestamp.isoformat(),
                    "market_id": trade.market_id,
                    "token_id": trade.token_id,
                    "side": trade.side,
                    "action": trade.action,
                    "price": f"{trade.price:.8f}",
                    "size": f"{trade.size:.8f}",
                    "notional": f"{trade.notional:.8f}",
                    "fee": f"{trade.fee:.8f}",
                    "realized_pnl": "" if trade.realized_pnl is None else f"{trade.realized_pnl:.8f}",
                    "reason": trade.reason,
                }
            )
