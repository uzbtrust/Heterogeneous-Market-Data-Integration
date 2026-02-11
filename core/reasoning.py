from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from openai import AsyncOpenAI

from core.config import settings
from core.exceptions import (
    LLMConnectionError,
    LLMResponseError,
)
from core.models import (
    MatchConfidence,
    ProductListing,
    ProductMatch,
    SearchQuery,
)

logger: logging.Logger = logging.getLogger(__name__)


QUERY_PARSE_SYSTEM: str = """\
You are a product-search query parser for Uzbekistan e-commerce.
Given the user's raw search query, extract structured fields.

Rules:
- product_name: the canonical product name (e.g. "Samsung Galaxy A33 5G")
- brand: manufacturer name if identifiable
- model: model identifier (e.g. "A33", "Redmi Note 12")
- storage_gb: storage in GB if mentioned (128, 256 …), as integer or null
- ram_gb: RAM in GB if mentioned, as integer or null
- color: color if mentioned, or null

Return ONLY valid JSON with exactly these keys. Use null for missing fields.
"""

ENTITY_ALIGNMENT_SYSTEM: str = """\
You are an entity-resolution expert for e-commerce products.
You must classify whether a scraped product listing matches a buyer's intent.

Classification rules:
- "exact": the listing IS the queried product (brand, model, and key specs match)
- "close": same product line but different configuration (e.g., 64GB vs 128GB)
- "accessory": a case, screen protector, charger, cable, or earphone for the product
- "unrelated": a completely different product

Always return ONLY valid JSON. No markdown, no explanation outside JSON.
"""

ENTITY_ALIGNMENT_USER: str = """\
USER QUERY (what the buyer wants):
  Product: {product_name}
  Brand: {brand}
  Model: {model}
  Storage: {storage_gb} GB
  RAM: {ram_gb} GB
  Color: {color}

LISTING FOUND ON {marketplace}:
  Title: "{title}"
  Price: {price_str}

Return JSON:
{{
  "confidence": "exact" | "close" | "accessory" | "unrelated",
  "reasoning": "<one sentence explaining your decision>",
  "extracted_specs": {{"storage_gb": <int|null>, "ram_gb": <int|null>, "color": <str|null>}},
  "relevance_score": <float between 0.0 and 1.0>
}}
"""


_KNOWN_BRANDS: list[str] = [
    "samsung", "xiaomi", "redmi", "apple", "iphone", "huawei",
    "realme", "oppo", "poco", "honor", "vivo", "oneplus", "google",
    "nokia", "motorola", "tecno", "infinix", "zte", "lenovo",
]

_STORAGE_VALUES: frozenset[int] = frozenset({32, 64, 128, 256, 512, 1024})
_RAM_VALUES: frozenset[int] = frozenset({2, 3, 4, 6, 8, 12, 16, 18, 24})

_ACCESSORY_KEYWORDS: tuple[str, ...] = (
    "чехол", "chexol", "case", "стекло", "glass", "зарядка",
    "charger", "кабель", "cable", "наушник", "earphone", "adapter",
    "protect", "cover", "plënka", "plyonka", "бампер", "bumper",
    "держатель", "holder", "пленка", "film", "strap", "ремешок",
)


class ReasoningEngine:

    def __init__(self, api_key: Optional[str] = None) -> None:
        key: str = api_key if api_key is not None else settings.XAI_API_KEY
        self._has_llm: bool = bool(key)

        if self._has_llm:
            self._client: Optional[AsyncOpenAI] = AsyncOpenAI(
                api_key=key,
                base_url=settings.XAI_BASE_URL,
            )
            logger.info(
                "ReasoningEngine initialized with %s (base=%s)",
                settings.LLM_MODEL,
                settings.XAI_BASE_URL,
            )
        else:
            self._client = None
            logger.warning(
                "No xAI API key configured — reasoning will use heuristic fallback"
            )

        self._model: str = settings.LLM_MODEL
        self._temperature: float = settings.LLM_TEMPERATURE

    # ── Public API ─────────────────────────────────────────────

    async def parse_query(self, raw_query: str) -> SearchQuery:
        if not self._has_llm:
            return self._heuristic_parse(raw_query)

        try:
            data: dict[str, Any] = await self._llm_json_call(
                system_prompt=QUERY_PARSE_SYSTEM,
                user_prompt=raw_query,
            )
            return SearchQuery(
                raw_query=raw_query,
                product_name=data.get("product_name") or raw_query,
                brand=data.get("brand"),
                model=data.get("model"),
                storage_gb=self._safe_int(data.get("storage_gb")),
                ram_gb=self._safe_int(data.get("ram_gb")),
                color=data.get("color"),
            )
        except (LLMConnectionError, LLMResponseError) as exc:
            logger.error("LLM query parsing failed: %s — falling back to heuristic", exc)
            return self._heuristic_parse(raw_query)

    async def align_entity(
        self,
        query: SearchQuery,
        listing: ProductListing,
    ) -> ProductMatch:
        if not self._has_llm:
            return self._heuristic_align(query, listing)

        user_prompt: str = ENTITY_ALIGNMENT_USER.format(
            product_name=query.product_name,
            brand=query.brand or "N/A",
            model=query.model or "N/A",
            storage_gb=query.storage_gb or "N/A",
            ram_gb=query.ram_gb or "N/A",
            color=query.color or "N/A",
            marketplace=listing.marketplace.value.upper(),
            title=listing.title,
            price_str=listing.price_str or str(listing.price),
        )

        try:
            data: dict[str, Any] = await self._llm_json_call(
                system_prompt=ENTITY_ALIGNMENT_SYSTEM,
                user_prompt=user_prompt,
            )
            confidence_raw: str = data.get("confidence", "unrelated")
            if confidence_raw not in {e.value for e in MatchConfidence}:
                confidence_raw = "unrelated"

            return ProductMatch(
                listing=listing,
                confidence=MatchConfidence(confidence_raw),
                reasoning=str(data.get("reasoning", "")),
                extracted_specs=data.get("extracted_specs") or {},
                relevance_score=self._clamp(float(data.get("relevance_score", 0.0))),
            )
        except (LLMConnectionError, LLMResponseError) as exc:
            logger.error(
                "LLM entity alignment failed for '%s': %s",
                listing.title, exc,
            )
            return self._heuristic_align(query, listing)

    # ── LLM internals ──────────────────────────────────────────

    async def _llm_json_call(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        assert self._client is not None

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as exc:
            raise LLMConnectionError(
                "Failed to reach xAI Grok API",
                detail=str(exc),
                context={"model": self._model},
            ) from exc

        raw_content: Optional[str] = response.choices[0].message.content
        if not raw_content:
            raise LLMResponseError(
                "LLM returned empty content",
                context={"model": self._model},
            )

        try:
            return json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise LLMResponseError(
                "LLM returned invalid JSON",
                detail=raw_content[:200],
                context={"model": self._model},
            ) from exc

    # ── Heuristic fallback ─────────────────────────────────────

    @staticmethod
    def _heuristic_parse(raw_query: str) -> SearchQuery:
        tokens: list[str] = raw_query.lower().split()

        brand: Optional[str] = None
        for candidate in _KNOWN_BRANDS:
            if candidate in tokens:
                brand = candidate.capitalize()
                break

        storage: Optional[int] = None
        ram: Optional[int] = None
        for token in tokens:
            # only consider tokens that actually carry a gb/гб suffix
            has_unit: bool = bool(re.search(r"(gb|гб)$", token, flags=re.IGNORECASE))
            if not has_unit:
                continue
            cleaned: str = re.sub(r"(gb|гб)$", "", token, flags=re.IGNORECASE)
            if cleaned.isdigit():
                val: int = int(cleaned)
                if val in _STORAGE_VALUES and storage is None:
                    storage = val
                elif val in _RAM_VALUES and ram is None:
                    ram = val

        return SearchQuery(
            raw_query=raw_query,
            product_name=raw_query,
            brand=brand,
            storage_gb=storage,
            ram_gb=ram,
        )

    @staticmethod
    def _heuristic_align(
        query: SearchQuery,
        listing: ProductListing,
    ) -> ProductMatch:
        title_lower: str = listing.title.lower()
        query_tokens: list[str] = query.raw_query.lower().split()
        token_count: int = max(len(query_tokens), 1)
        hit_count: int = sum(1 for t in query_tokens if t in title_lower)
        ratio: float = hit_count / token_count

        is_accessory: bool = any(kw in title_lower for kw in _ACCESSORY_KEYWORDS)

        if is_accessory:
            confidence: MatchConfidence = MatchConfidence.ACCESSORY
            score: float = 0.1
        elif ratio >= 0.7:
            confidence = MatchConfidence.EXACT
            score = ratio
        elif ratio >= 0.4:
            confidence = MatchConfidence.CLOSE
            score = ratio
        else:
            confidence = MatchConfidence.UNRELATED
            score = ratio

        return ProductMatch(
            listing=listing,
            confidence=confidence,
            reasoning=f"Heuristic: {hit_count}/{token_count} query tokens found in title",
            extracted_specs={},
            relevance_score=round(score, 2),
        )

    # ── Utilities ──────────────────────────────────────────────

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))
