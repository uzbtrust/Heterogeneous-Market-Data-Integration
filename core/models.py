from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, computed_field


class Marketplace(str, Enum):
    UZUM = "uzum"
    ASAXIY = "asaxiy"
    OLCHA = "olcha"


class MatchConfidence(str, Enum):
    EXACT = "exact"
    CLOSE = "close"
    ACCESSORY = "accessory"
    UNRELATED = "unrelated"


class SearchQuery(BaseModel):
    raw_query: str = Field(..., description="Original user input")
    product_name: str = Field(..., description="Extracted product name")
    brand: Optional[str] = Field(None, description="Detected brand")
    model: Optional[str] = Field(None, description="Detected model identifier")
    storage_gb: Optional[int] = Field(None, description="Storage capacity in GB")
    ram_gb: Optional[int] = Field(None, description="RAM capacity in GB")
    color: Optional[str] = Field(None, description="Desired color")


class ProductListing(BaseModel):
    title: str
    price: Optional[int] = Field(None, description="Price in UZS")
    price_str: str = Field("", description="Original price string from page")
    url: str = Field(..., description="Direct product link")
    image_url: Optional[str] = None
    marketplace: Marketplace
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    in_stock: bool = True
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @computed_field
    @property
    def listing_id(self) -> str:
        """Deterministic ID derived from marketplace + URL."""
        raw: str = f"{self.marketplace.value}:{self.url}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class ProductMatch(BaseModel):
    listing: ProductListing
    confidence: MatchConfidence
    reasoning: str = Field("", description="LLM explanation for the match decision")
    extracted_specs: dict[str, Any] = Field(
        default_factory=dict,
        description="Specs extracted by LLM (storage_gb, ram_gb, color)",
    )
    relevance_score: float = Field(
        0.0, ge=0.0, le=1.0, description="Composite relevance score"
    )


class AgentResult(BaseModel):
    query: SearchQuery
    matches: list[ProductMatch] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    total_scraped: int = 0
    total_matched: int = 0
    duration_seconds: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @computed_field
    @property
    def best_price(self) -> Optional[int]:
        """Lowest price among EXACT and CLOSE matches only."""
        prices: list[int] = [
            m.listing.price
            for m in self.matches
            if m.confidence in (MatchConfidence.EXACT, MatchConfidence.CLOSE)
            and m.listing.price is not None
        ]
        return min(prices) if prices else None
