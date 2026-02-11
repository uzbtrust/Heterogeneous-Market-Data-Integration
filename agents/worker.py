from __future__ import annotations

import logging
import time
from typing import Type

from core.exceptions import ScraperException
from core.models import Marketplace, ProductListing
from tools.asaxiy import AsaxiyScraper
from tools.base import BaseScraper
from tools.olcha import OlchaScraper
from tools.uzum import UzumScraper

logger: logging.Logger = logging.getLogger(__name__)

_SCRAPER_REGISTRY: dict[Marketplace, Type[BaseScraper]] = {
    Marketplace.UZUM: UzumScraper,
    Marketplace.ASAXIY: AsaxiyScraper,
    Marketplace.OLCHA: OlchaScraper,
}


class WorkerAgent:

    def __init__(self, marketplace: Marketplace) -> None:
        self.marketplace: Marketplace = marketplace
        self._scraper_cls: Type[BaseScraper] = _SCRAPER_REGISTRY[marketplace]

    def __repr__(self) -> str:
        return f"WorkerAgent(marketplace={self.marketplace.value})"

    async def execute(self, query: str) -> list[ProductListing]:
        t0: float = time.perf_counter()
        logger.info(
            "[Worker:%s] Starting scrape for '%s'",
            self.marketplace.value, query,
        )

        listings: list[ProductListing] = []
        try:
            async with self._scraper_cls() as scraper:
                listings = await scraper.scrape(query)
        except ScraperException as exc:
            logger.error(
                "[Worker:%s] Scraper exception: %r",
                self.marketplace.value, exc,
            )
        except Exception as exc:
            logger.error(
                "[Worker:%s] Unexpected error: %s",
                self.marketplace.value, exc,
            )

        elapsed: float = time.perf_counter() - t0
        logger.info(
            "[Worker:%s] Finished in %.1fs — %d listings",
            self.marketplace.value, elapsed, len(listings),
        )
        return listings
