from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from agents.worker import WorkerAgent
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

    async def run(self, raw_query: str) -> AgentResult:
        t0: float = time.perf_counter()
        errors: list[str] = []

        # Step 1 — parse query via LLM (or heuristic)
        logger.info("[Master] Parsing query: '%s'", raw_query)
        query: SearchQuery = await self.reasoning.parse_query(raw_query)
        logger.info("[Master] Parsed → %s", query.model_dump_json(indent=2))

        # Step 2 — dispatch workers in parallel
        logger.info("[Master] Dispatching %d workers in parallel", len(self.workers))
        scrape_tasks = [w.execute(query.raw_query) for w in self.workers]
        results_per_worker = await asyncio.gather(*scrape_tasks, return_exceptions=True)

        all_listings: list[ProductListing] = []
        for worker, result in zip(self.workers, results_per_worker):
            if isinstance(result, BaseException):
                msg: str = f"{worker.marketplace.value}: {result}"
                logger.error("[Master] Worker error: %s", msg)
                errors.append(msg)
            else:
                all_listings.extend(result)

        total_scraped: int = len(all_listings)
        logger.info("[Master] Total raw listings: %d", total_scraped)

        # Step 3 — entity alignment (LLM or heuristic per listing)
        sem = asyncio.Semaphore(settings.LLM_CONCURRENCY_LIMIT)

        async def _align_with_limit(listing: ProductListing) -> ProductMatch:
            async with sem:
                return await self.reasoning.align_entity(query, listing)

        logger.info("[Master] Running entity alignment on %d listings", total_scraped)
        align_tasks = [_align_with_limit(listing) for listing in all_listings]
        matches: list[ProductMatch] = await asyncio.gather(*align_tasks)

        # Step 4 — rank: exact first, then close, then accessories
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
