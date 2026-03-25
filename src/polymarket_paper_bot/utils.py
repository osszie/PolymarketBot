"""Shared helpers: retries, IDs, JSON, and safe numeric parsing."""

from __future__ import annotations

import json
import random
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

T = TypeVar("T")


def new_id(prefix: str) -> str:
    """Return a short unique identifier suitable for logs and CSV keys."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def parse_json_list(raw: Any) -> list[Any]:
    """
    Parse Gamma fields that may arrive as JSON-encoded strings (e.g. clobTokenIds).

    Returns an empty list on failure — upstream shapes vary by endpoint/version.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, str):
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return list(val) if isinstance(val, list) else []
    return []


def safe_float(value: Any, default: float | None = None) -> float | None:
    """Parse a float from assorted scalar types; return default if not possible."""
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp ``value`` to ``[lo, hi]``."""
    return max(lo, min(hi, value))


def exponential_backoff_sleep(attempt: int, base: float = 0.25, cap: float = 8.0) -> None:
    """Sleep with exponential backoff: base * 2^attempt, capped."""
    delay = min(cap, base * (2**attempt))
    time.sleep(delay)


def retry_http(
    op: Callable[[], T],
    *,
    max_retries: int,
    is_transient: Callable[[Exception], bool],
    log_warning: Callable[[str], None],
) -> T:
    """
    Retry ``op`` on transient failures with exponential backoff.

    ``is_transient`` should return True for network/timeouts/5xx-like conditions.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return op()
        except Exception as exc:  # noqa: BLE001 — boundary for HTTP client
            last_exc = exc
            if attempt >= max_retries or not is_transient(exc):
                raise
            log_warning(f"transient error (attempt {attempt + 1}/{max_retries}): {exc!r}")
            exponential_backoff_sleep(attempt)
    assert last_exc is not None
    raise last_exc


def deterministic_rng(seed: int | None) -> random.Random:
    """Return a ``random.Random`` instance; if seed is None, use system entropy."""
    return random.Random(seed)


def iter_batches(items: list[T], batch_size: int) -> Iterator[list[T]]:
    """Yield successive slices of ``items``."""
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]
