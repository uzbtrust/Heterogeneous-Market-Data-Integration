from __future__ import annotations

import pytest

from core.models import MatchConfidence, Marketplace, ProductListing
from core.reasoning import ReasoningEngine


@pytest.fixture
def engine() -> ReasoningEngine:
    return ReasoningEngine(api_key="")


@pytest.fixture
def sample_listing() -> ProductListing:
    return ProductListing(
        title="Samsung Galaxy A33 5G 6/128GB Black Smartphone",
        price=3_290_000,
        price_str="3 290 000 сўм",
        url="https://uzum.uz/product/samsung-a33",
        marketplace=Marketplace.UZUM,
    )


@pytest.fixture
def accessory_listing() -> ProductListing:
    return ProductListing(
        title="Чехол для Samsung Galaxy A33 силиконовый чёрный",
        price=45_000,
        price_str="45 000 сўм",
        url="https://uzum.uz/product/chexol-a33",
        marketplace=Marketplace.UZUM,
    )


class TestHeuristicQueryParsing:

    @pytest.mark.asyncio
    async def test_parse_samsung(self, engine: ReasoningEngine) -> None:
        query = await engine.parse_query("Samsung Galaxy A33 5G 128GB")
        assert query.brand == "Samsung"
        assert query.storage_gb == 128

    @pytest.mark.asyncio
    async def test_parse_xiaomi_with_ram(self, engine: ReasoningEngine) -> None:
        query = await engine.parse_query("Xiaomi Redmi Note 12 256GB 8GB")
        assert query.brand == "Xiaomi"
        assert query.storage_gb == 256
        assert query.ram_gb == 8

    @pytest.mark.asyncio
    async def test_parse_unknown_brand(self, engine: ReasoningEngine) -> None:
        query = await engine.parse_query("random product 64GB")
        assert query.brand is None
        assert query.storage_gb == 64

    @pytest.mark.asyncio
    async def test_parse_preserves_raw_query(self, engine: ReasoningEngine) -> None:
        raw: str = "iPhone 15 Pro Max 256GB"
        query = await engine.parse_query(raw)
        assert query.raw_query == raw


class TestHeuristicEntityAlignment:

    @pytest.mark.asyncio
    async def test_exact_match(
        self, engine: ReasoningEngine, sample_listing: ProductListing,
    ) -> None:
        query = await engine.parse_query("Samsung Galaxy A33 5G 128GB")
        match = await engine.align_entity(query, sample_listing)
        assert match.confidence in (MatchConfidence.EXACT, MatchConfidence.CLOSE)
        assert match.relevance_score > 0.5

    @pytest.mark.asyncio
    async def test_accessory_detection(
        self, engine: ReasoningEngine, accessory_listing: ProductListing,
    ) -> None:
        query = await engine.parse_query("Samsung Galaxy A33 5G 128GB")
        match = await engine.align_entity(query, accessory_listing)
        assert match.confidence == MatchConfidence.ACCESSORY
        assert match.relevance_score < 0.5

    @pytest.mark.asyncio
    async def test_unrelated_product(self, engine: ReasoningEngine) -> None:
        query = await engine.parse_query("Samsung Galaxy A33 5G 128GB")
        listing = ProductListing(
            title="Dyson V15 Detect Vacuum Cleaner",
            price=8_000_000,
            url="https://uzum.uz/product/dyson-v15",
            marketplace=Marketplace.UZUM,
        )
        match = await engine.align_entity(query, listing)
        assert match.confidence == MatchConfidence.UNRELATED


class TestExceptionHierarchy:

    def test_app_exception_base(self) -> None:
        from core.exceptions import AppException
        exc = AppException("test", detail="detail", context={"key": "val"})
        assert exc.message == "test"
        assert exc.detail == "detail"
        assert exc.context == {"key": "val"}

    def test_scraper_exception_hierarchy(self) -> None:
        from core.exceptions import (
            AppException,
            ExtractionError,
            MarketplaceUnavailable,
            NavigationError,
            ScraperException,
        )
        assert issubclass(ScraperException, AppException)
        assert issubclass(NavigationError, ScraperException)
        assert issubclass(ExtractionError, ScraperException)
        assert issubclass(MarketplaceUnavailable, ScraperException)

    def test_reasoning_exception_hierarchy(self) -> None:
        from core.exceptions import (
            AppException,
            LLMConnectionError,
            LLMResponseError,
            QueryParseError,
            ReasoningException,
        )
        assert issubclass(ReasoningException, AppException)
        assert issubclass(LLMConnectionError, ReasoningException)
        assert issubclass(LLMResponseError, ReasoningException)
        assert issubclass(QueryParseError, ReasoningException)

    def test_pipeline_exception_hierarchy(self) -> None:
        from core.exceptions import (
            AppException,
            OrchestratorError,
            PipelineException,
            WorkerError,
        )
        assert issubclass(PipelineException, AppException)
        assert issubclass(WorkerError, PipelineException)
        assert issubclass(OrchestratorError, PipelineException)
