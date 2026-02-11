from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

logger: logging.Logger = logging.getLogger(__name__)

_ENV_PATH: Final[Path] = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


class Settings:

    # LLM
    XAI_API_KEY: str = os.getenv("XAI_API_KEY", "")
    XAI_BASE_URL: str = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "grok-3-mini")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))

    # Scraping
    SCRAPE_TIMEOUT_MS: int = int(os.getenv("SCRAPE_TIMEOUT_MS", "30000"))
    MAX_RESULTS_PER_SITE: int = int(os.getenv("MAX_RESULTS_PER_SITE", "15"))
    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
    USER_AGENT: str = (
        "Mozilla/5.0 (Macintosh; Apple Silicon Mac OS X) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    )

    # Concurrency
    MAX_CONCURRENT_SCRAPERS: int = int(os.getenv("MAX_CONCURRENT_SCRAPERS", "3"))
    LLM_CONCURRENCY_LIMIT: int = int(os.getenv("LLM_CONCURRENCY_LIMIT", "10"))

    # UI
    APP_TITLE: str = "UzMarket Intelligence Agent"
    APP_SUBTITLE: str = "Autonomous Multi-Marketplace Product Search"

    def __repr__(self) -> str:
        return (
            f"Settings(model={self.LLM_MODEL}, base_url={self.XAI_BASE_URL}, "
            f"headless={self.HEADLESS}, max_results={self.MAX_RESULTS_PER_SITE})"
        )


settings: Final[Settings] = Settings()
