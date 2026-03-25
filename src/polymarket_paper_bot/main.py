"""CLI entrypoint: paper trading, scans, snapshot capture, and replay."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from polymarket_paper_bot.config import config_to_log_dict, load_config
from polymarket_paper_bot.logger import setup_logging
from polymarket_paper_bot.runner.bot import TradingBot
from polymarket_paper_bot.runner.snapshot import capture_snapshot_file


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Polymarket public-data paper trading bot")
    p.add_argument(
        "--mode",
        choices=["paper", "scan", "replay", "snapshot"],
        default="paper",
        help="paper loop, one-shot scan, snapshot replay, or capture JSON snapshot",
    )
    p.add_argument(
        "--iterations",
        type=int,
        default=20,
        help="paper/replay ticks or scan candidate count (depending on mode)",
    )
    p.add_argument(
        "--snapshot-file",
        type=str,
        default=str(Path("data") / "snapshot.json"),
        help="snapshot path for replay/capture modes",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    config = load_config()

    if config.enable_live_adapter:
        print(
            "ENABLE_LIVE_ADAPTER is not supported by this repository build. "
            "Refusing to start. Keep paper mode (default).",
            file=sys.stderr,
        )
        return 2

    config.ensure_runtime_dirs()
    log = setup_logging(config.log_level)
    log.info("starting | config=%s", config_to_log_dict(config))

    bot = TradingBot(config)
    snap_path = Path(args.snapshot_file)

    try:
        if args.mode == "scan":
            bot.run_scan(top_n=int(args.iterations))
        elif args.mode == "paper":
            bot.run_paper_loop(iterations=int(args.iterations))
        elif args.mode == "replay":
            if not snap_path.exists():
                log.error("snapshot file not found: %s", snap_path)
                return 1
            bot.run_replay(snapshot_path=snap_path, iterations=int(args.iterations))
        elif args.mode == "snapshot":
            out = capture_snapshot_file(
                config,
                gamma=bot.gamma,
                clob=bot.clob,
                out_path=snap_path,
                markets_limit=int(config.max_markets_to_scan),
            )
            log.info("wrote snapshot: %s", out)
        else:
            raise AssertionError("unhandled mode")
    finally:
        bot.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
