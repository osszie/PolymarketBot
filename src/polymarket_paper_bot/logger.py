"""Structured console logging setup."""

from __future__ import annotations

import logging
import sys
from typing import Any


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Configure root logging for CLI runs.

    Uses a concise format suitable for local development and log aggregation.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)
    root.addHandler(handler)
    # Keep third-party HTTP libraries quiet unless debugging.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return logging.getLogger("polymarket_paper_bot")


def log_extra(logger: logging.Logger, message: str, **fields: Any) -> None:
    """Log a message with optional structured fields (flattened into the message)."""
    if not fields:
        logger.info(message)
        return
    parts = [f"{k}={fields[k]!r}" for k in sorted(fields)]
    logger.info("%s | %s", message, " ".join(parts))
