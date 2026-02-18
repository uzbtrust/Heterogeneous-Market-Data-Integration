from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from agents.worker import WorkerAgent
from core.cache import get_from_cache, set_to_cache
from core.config import settings
from core.models import (
    AgentResult,
    MatchConfidence,
    Marketplace,
    ProductListing,
    ProductMatch,
    SearchQuery,
)
from core.reasoning import ReasoningEngine

logger: logging.Logger = logging.getLogger(__name__)


class MasterAgent:

    def __init__(
        self,
        reasoning_engine: Optional[ReasoningEngine] = None,
    ) -> None:
        self.reasoning: ReasoningEngine = reasoning_engine or ReasoningEngine()
        self.workers: list[WorkerAgent] = [
            WorkerAgent(Marketplace.UZUM),
            WorkerAgent(Marketplace.ASAXIY),
            WorkerAgent(Marketplace.OLCHA),
        ]

    async def _scrape(
        self,
        query: SearchQuery,
        errors: list[str],
    ) -> tuple[list[ProductListing], list[str]]:
        """Dispatch all marketplace workers in parallel and aggregate results."""
        logger.info("[Master] Dispatching %d workers in parallel", len(self.workers))
        scrape_tasks = [w.execute(query.raw_query) for w in self.workers]
        results_per_worker = await asyncio.gather(*scrape_tasks, return_exceptions=True)

        listings: list[ProductListing] = []
        for worker, result in zip(self.workers, results_per_worker):
            if isinstance(result, BaseException):
                msg: str = f"{worker.marketplace.value}: {result}"
                logger.error("[Master] Worker error: %s", msg)
                errors.append(msg)
            else:
                listings.extend(result)

        return listings, errors

    async def run(self, raw_query: str, no_cache: bool = False) -> AgentResult:
        t0: float = time.perf_counter()
        errors: list[str] = []

        logger.info("[Master] Parsing query: '%s'", raw_query)
        query: SearchQuery = await self.reasoning.parse_query(raw_query)
        logger.info("[Master] Parsed → %s", query.model_dump_json(indent=2))

        all_listings: list[ProductListing] = []
        if not no_cache:
            cached = await get_from_cache(raw_query)
            if cached is not None:
                logger.info(
                    "[Master] Cache hit — %d listings loaded, skipping scrape",
                    len(cached),
                )
                all_listings = cached
            else:
                logger.info("[Master] Cache miss — dispatching workers")
                all_listings, errors = await self._scrape(query, errors)
                await set_to_cache(raw_query, all_listings)
                logger.info(
                    "[Master] Cache stored — %d listings cached (TTL=%ds)",
                    len(all_listings),
                    settings.CACHE_TTL_SECONDS,
                )
        else:
            logger.info("[Master] Cache disabled (--no-cache) — dispatching workers")
            all_listings, errors = await self._scrape(query, errors)

        total_scraped: int = len(all_listings)
        logger.info("[Master] Total raw listings: %d", total_scraped)

        sem = asyncio.Semaphore(settings.LLM_CONCURRENCY_LIMIT)

        async def _align_with_limit(listing: ProductListing) -> ProductMatch:
            async with sem:
                return await self.reasoning.align_entity(query, listing)

        logger.info("[Master] Running entity alignment on %d listings", total_scraped)
        align_tasks = [_align_with_limit(listing) for listing in all_listings]
        matches: list[ProductMatch] = await asyncio.gather(*align_tasks)

        relevant: list[ProductMatch] = [
            m for m in matches
            if m.confidence in (MatchConfidence.EXACT, MatchConfidence.CLOSE)
        ]
        relevant.sort(
            key=lambda m: (
                0 if m.confidence == MatchConfidence.EXACT else 1,
                -m.relevance_score,
                m.listing.price if m.listing.price is not None else float("inf"),
            )
        )

        accessories: list[ProductMatch] = [
            m for m in matches if m.confidence == MatchConfidence.ACCESSORY
        ]
        all_ranked: list[ProductMatch] = relevant + accessories

        elapsed: float = time.perf_counter() - t0
        logger.info(
            "[Master] Done in %.1fs — %d relevant, %d accessories",
            elapsed, len(relevant), len(accessories),
        )

        return AgentResult(
            query=query,
            matches=all_ranked,
            errors=errors,
            total_scraped=total_scraped,
            total_matched=len(relevant),
            duration_seconds=round(elapsed, 2),
        )
