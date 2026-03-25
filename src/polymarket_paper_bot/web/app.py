"""Flask application factory for the trades dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template

from polymarket_paper_bot.config import AppConfig
from polymarket_paper_bot.storage.csv_logger import CsvTradeLogger
from polymarket_paper_bot.storage.state_store import StateStore
from polymarket_paper_bot.web.data import (
    load_bot_state_json,
    load_trades_csv,
    summarize_from_state,
    trades_newest_first,
)


def _template_dir() -> Path:
    return Path(__file__).resolve().parent / "templates"


def create_app(config: AppConfig | None = None) -> Flask:
    """Create Flask app wired to ``config`` paths (``DATA_DIR``)."""
    if config is None:
        from polymarket_paper_bot.config import load_config

        config = load_config()

    app = Flask(
        __name__,
        template_folder=str(_template_dir()),
        static_folder=str(_template_dir() / "static"),
        static_url_path="/static",
    )

    trades_path = CsvTradeLogger(config).path
    state_path = StateStore(config).path

    @app.route("/")
    def index() -> str:
        raw_rows = load_trades_csv(trades_path)
        rows = trades_newest_first(raw_rows)
        state_raw = load_bot_state_json(state_path)
        summary = summarize_from_state(state_raw)
        return render_template(
            "dashboard_v2.html",
            config=config,
            trades=rows,
            summary=summary,
            trades_path=str(trades_path),
            state_path=str(state_path),
        )

    @app.get("/api/trades")
    def api_trades() -> Any:
        raw_rows = load_trades_csv(trades_path)
        return jsonify({"trades": trades_newest_first(raw_rows)})

    @app.get("/api/state")
    def api_state() -> Any:
        state_raw = load_bot_state_json(state_path)
        return jsonify({"state": state_raw, "summary": summarize_from_state(state_raw)})

    return app


def run_server(config: AppConfig, *, host: str, port: int, debug: bool = False) -> None:
    """Run the development server (blocking)."""
    app = create_app(config)
    app.run(host=host, port=port, debug=debug, use_reloader=debug)
