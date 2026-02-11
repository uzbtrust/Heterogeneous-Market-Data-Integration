from __future__ import annotations

from typing import Optional

import pytest

from core.models import (
    AgentResult,
    MatchConfidence,
    Marketplace,
    ProductListing,
    ProductMatch,
    SearchQuery,
)


class TestSearchQuery:

    def test_creation_with_all_fields(self) -> None:
        q: SearchQuery = SearchQuery(
            raw_query="Samsung A33 128GB",
            product_name="Samsung Galaxy A33",
            brand="Samsung",
            model="A33",
            storage_gb=128,
        )
        assert q.brand == "Samsung"
        assert q.storage_gb == 128
        assert q.ram_gb is None

    def test_missing_optional_fields_default_to_none(self) -> None:
        q: SearchQuery = SearchQuery(raw_query="test", product_name="test")
        assert q.brand is None
        assert q.model is None
        assert q.color is None


class TestProductListing:

    def test_listing_id_deterministic(self) -> None:
        listing1: ProductListing = ProductListing(
            title="Test Product",
            price=1000000,
            url="https://uzum.uz/product/123",
            marketplace=Marketplace.UZUM,
        )
        listing2: ProductListing = ProductListing(
            title="Different Title",
            price=2000000,
            url="https://uzum.uz/product/123",
            marketplace=Marketplace.UZUM,
        )
        assert listing1.listing_id == listing2.listing_id

    def test_different_urls_produce_different_ids(self) -> None:
        l1: ProductListing = ProductListing(
            title="P", url="https://uzum.uz/product/1", marketplace=Marketplace.UZUM,
        )
        l2: ProductListing = ProductListing(
            title="P", url="https://uzum.uz/product/2", marketplace=Marketplace.UZUM,
        )
        assert l1.listing_id != l2.listing_id


class TestAgentResult:

    def test_best_price_from_exact_matches(self) -> None:
        query: SearchQuery = SearchQuery(raw_query="test", product_name="test")
        m1: ProductMatch = ProductMatch(
            listing=ProductListing(
                title="A", price=5_000_000,
                url="https://a.uz/1", marketplace=Marketplace.UZUM,
            ),
            confidence=MatchConfidence.EXACT,
            relevance_score=0.9,
        )
        m2: ProductMatch = ProductMatch(
            listing=ProductListing(
                title="B", price=3_000_000,
                url="https://b.uz/2", marketplace=Marketplace.ASAXIY,
            ),
            confidence=MatchConfidence.EXACT,
            relevance_score=0.8,
        )
        result: AgentResult = AgentResult(query=query, matches=[m1, m2])
        assert result.best_price == 3_000_000

    def test_best_price_excludes_accessories(self) -> None:
        query: SearchQuery = SearchQuery(raw_query="test", product_name="test")
        m: ProductMatch = ProductMatch(
            listing=ProductListing(
                title="Case", price=50_000,
                url="https://a.uz/1", marketplace=Marketplace.OLCHA,
            ),
            confidence=MatchConfidence.ACCESSORY,
            relevance_score=0.1,
        )
        result: AgentResult = AgentResult(query=query, matches=[m])
        assert result.best_price is None

    def test_best_price_none_when_no_matches(self) -> None:
        query: SearchQuery = SearchQuery(raw_query="test", product_name="test")
        result: AgentResult = AgentResult(query=query)
        assert result.best_price is None


class TestMatchConfidence:

    def test_enum_values(self) -> None:
        assert MatchConfidence.EXACT.value == "exact"
        assert MatchConfidence.CLOSE.value == "close"
        assert MatchConfidence.ACCESSORY.value == "accessory"
        assert MatchConfidence.UNRELATED.value == "unrelated"
