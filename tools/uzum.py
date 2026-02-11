from __future__ import annotations

import logging
import re
from typing import Any, Optional
from urllib.parse import quote_plus

from core.config import settings
from core.exceptions import ExtractionError, NavigationError
from core.models import Marketplace, ProductListing
from tools.base import BaseScraper

logger: logging.Logger = logging.getLogger(__name__)

_BASE_URL: str = "https://uzum.uz"
_SEARCH_URL: str = _BASE_URL + "/search?query={query}"

_EXTRACTION_JS: str = """
() => {
    const cards = document.querySelectorAll(
        '[data-test-id="product-card"], .product-card, .card-wrapper a[href*="/product/"]'
    );
    const results = [];
    for (const card of cards) {
        const link = card.closest('a') || card.querySelector('a');
        const href = link ? link.getAttribute('href') : null;
        const titleEl = card.querySelector(
            '[data-test-id="product-title"], .product-card__title, .subtitle-item, span'
        );
        const priceEl = card.querySelector(
            '[data-test-id="product-price"], .product-card__price, .price'
        );
        const imgEl = card.querySelector('img');
        results.push({
            title: titleEl ? titleEl.innerText.trim() : '',
            price_str: priceEl ? priceEl.innerText.trim() : '',
            href: href || '',
            img: imgEl ? (imgEl.src || imgEl.dataset.src || '') : '',
        });
    }
    return results;
}
"""


class UzumScraper(BaseScraper):

    marketplace = Marketplace.UZUM

    async def scrape(self, query: str) -> list[ProductListing]:
        listings: list[ProductListing] = []
        url: str = _SEARCH_URL.format(query=quote_plus(query))
        logger.info("[Uzum] Searching: %s", url)

        ctx = await self._new_context()
        page = await ctx.new_page()

        try:
            try:
                if not await self._safe_goto(page, url):
                    return listings
            except NavigationError:
                return listings

            try:
                await page.wait_for_selector(
                    "[data-test-id='product-card'], .product-card, a[href*='/product/']",
                    timeout=15000,
                )
            except Exception:
                logger.warning("[Uzum] Product cards did not appear — page may be empty or blocked")
                return listings

            await page.wait_for_timeout(2000)
            raw_items: list[dict[str, Any]] = await page.evaluate(_EXTRACTION_JS)

            for item in raw_items[: settings.MAX_RESULTS_PER_SITE]:
                if not item.get("title") or not item.get("href"):
                    continue
                href: str = item["href"]
                if href.startswith("/"):
                    href = _BASE_URL + href

                listings.append(
                    ProductListing(
                        title=item["title"],
                        price=self._parse_price(item.get("price_str", "")),
                        price_str=item.get("price_str", ""),
                        url=href,
                        image_url=item.get("img") or None,
                        marketplace=self.marketplace,
                    )
                )

            logger.info("[Uzum] Extracted %d listings", len(listings))

        except ExtractionError:
            raise
        except Exception as exc:
            logger.error("[Uzum] Unexpected scrape error: %s", exc)
        finally:
            await page.close()
            await ctx.close()

        return listings

    @staticmethod
    def _parse_price(price_str: str) -> Optional[int]:
        digits: str = re.sub(r"[^\d]", "", price_str)
        return int(digits) if digits else None
