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

_BASE_URL: str = "https://asaxiy.uz"
_SEARCH_URL: str = _BASE_URL + "/product?key={query}"

_EXTRACTION_JS: str = """
() => {
    const cards = document.querySelectorAll(
        '.product__item, .product-card, .col-6.col-xl-3.col-md-4'
    );
    const results = [];
    for (const card of cards) {
        const link = card.querySelector('a[href*="/product/"]');
        const href = link ? link.getAttribute('href') : null;
        const titleEl = card.querySelector(
            '.product__item__info a, .product-title, .goods-name, a[href*="/product/"]'
        );
        const priceEl = card.querySelector(
            '.product__item-price, .price, .product-price'
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


class AsaxiyScraper(BaseScraper):

    marketplace = Marketplace.ASAXIY

    async def scrape(self, query: str) -> list[ProductListing]:
        listings: list[ProductListing] = []
        url: str = _SEARCH_URL.format(query=quote_plus(query))
        logger.info("[Asaxiy] Searching: %s", url)

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
                    ".product__item, .product-card, a[href*='/product/']",
                    timeout=15000,
                )
            except Exception:
                logger.warning("[Asaxiy] Product cards not found")
                return listings

            await page.wait_for_timeout(1500)
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

            logger.info("[Asaxiy] Extracted %d listings", len(listings))

        except ExtractionError:
            raise
        except Exception as exc:
            logger.error("[Asaxiy] Unexpected scrape error: %s", exc)
        finally:
            await page.close()
            await ctx.close()

        return listings

    @staticmethod
    def _parse_price(price_str: str) -> Optional[int]:
        # strip installment suffixes like "x 12 мес" before parsing
        clean: str = price_str.split("x")[0].split("\u00d7")[0]
        digits: str = re.sub(r"[^\d]", "", clean)
        return int(digits) if digits else None
