from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger: logging.Logger = logging.getLogger("main")


def _run_cli(query: str) -> None:
    from agents.master import MasterAgent
    from core.models import AgentResult
    from core.reasoning import ReasoningEngine

    engine: ReasoningEngine = ReasoningEngine()
    agent: MasterAgent = MasterAgent(reasoning_engine=engine)

    logger.info("Starting search for: '%s'", query)
    result: AgentResult = asyncio.run(agent.run(query))

    logger.info("=" * 60)
    logger.info("SEARCH RESULTS")
    logger.info("=" * 60)
    logger.info("Query:         %s", result.query.raw_query)
    logger.info("Brand:         %s", result.query.brand or "\u2014")
    logger.info("Model:         %s", result.query.model or "\u2014")
    logger.info("Storage:       %s GB", result.query.storage_gb or "\u2014")
    logger.info("Total scraped: %d", result.total_scraped)
    logger.info("Matched:       %d", result.total_matched)
    if result.best_price:
        logger.info("Best price:    %s UZS", f"{result.best_price:,}")
    else:
        logger.info("Best price:    \u2014")
    logger.info("Duration:      %ss", result.duration_seconds)
    logger.info("-" * 60)

    for i, m in enumerate(result.matches, 1):
        conf_tag: str = m.confidence.value.upper()
        price_display: str = (
            f"{m.listing.price:,} UZS" if m.listing.price else m.listing.price_str
        )
        logger.info("")
        logger.info("  [%d] [%s] %s", i, conf_tag, m.listing.title)
        logger.info("      Price: %s", price_display)
        logger.info("      Store: %s", m.listing.marketplace.value)
        logger.info("      Score: %.0f%%", m.relevance_score * 100)
        logger.info("      Link:  %s", m.listing.url)
        if m.reasoning:
            logger.info("      Why:   %s", m.reasoning)

    if result.errors:
        logger.warning("Errors encountered:")
        for err in result.errors:
            logger.warning("  - %s", err)

    json_path: str = "last_result.json"
    output: dict = result.model_dump(mode="json")
    with open(json_path, "w", encoding="utf-8") as fp:
        json.dump(output, fp, ensure_ascii=False, indent=2)
    logger.info("Full JSON saved to %s", json_path)


def _run_ui() -> None:
    ui_path: str = str(Path(__file__).parent / "ui" / "app.py")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", ui_path],
        check=True,
    )


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Universal Market Intelligence Agent for Uzbekistan E-commerce",
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Product search query (CLI mode)",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Launch Streamlit web interface",
    )

    args: argparse.Namespace = parser.parse_args()

    if args.ui:
        _run_ui()
    elif args.query:
        _run_cli(args.query)
    else:
        parser.print_help()
        logger.info("Examples:")
        logger.info('  python main.py "Samsung Galaxy A33 5G 128GB"')
        logger.info("  python main.py --ui")
        sys.exit(1)


if __name__ == "__main__":
    main()
