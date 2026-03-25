"""Flask dashboard smoke tests."""

from __future__ import annotations

from pathlib import Path

from polymarket_paper_bot.config import load_config
from polymarket_paper_bot.web.app import create_app


def test_dashboard_renders(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cfg = load_config(
        {
            "DATA_DIR": str(data_dir),
            "LOGS_DIR": str(tmp_path / "logs"),
        }
    )
    app = create_app(cfg)
    client = app.test_client()
    r = client.get("/")
    assert r.status_code == 200
    assert b"Polymarket Bot Dashboard" in r.data

    j = client.get("/api/trades").get_json()
    assert j is not None
    assert j["trades"] == []
