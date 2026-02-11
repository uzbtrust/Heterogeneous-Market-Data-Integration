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

_BASE_URL: str = "https://olcha.uz"
_SEARCH_URL: str = _BASE_URL + "/search?query={query}"

_EXTRACTION_JS: str = """
() => {
    const cards = document.querySelectorAll(
        '.product-card, .product-card._md, .product-listing__item'
    );
    const results = [];
    for (const card of cards) {
        const link = card.querySelector('a[href]') || card.closest('a');
        const href = link ? link.getAttribute('href') : null;
        const titleEl = card.querySelector(
            '.product-card__brand .goods-name, .product-card__title, .product-name'
        );
        const priceEl = card.querySelector(
            '.price, .product-card__price'
        );
        const imgEl = card.querySelector('img');
        results.push({
            title: titleEl
                ? titleEl.innerText.trim()
                : (link ? link.innerText.trim().split('\\n')[0] : ''),
            price_str: priceEl ? priceEl.innerText.trim() : '',
            href: href || '',
            img: imgEl ? (imgEl.src || imgEl.dataset.src || '') : '',
        });
    }
    return results;
}
"""


class OlchaScraper(BaseScraper):

    marketplace = Marketplace.OLCHA

    async def scrape(self, query: str) -> list[ProductListing]:
        listings: list[ProductListing] = []
        url: str = _SEARCH_URL.format(query=quote_plus(query))
        logger.info("[Olcha] Searching: %s", url)

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
                    ".product-card, .product-card._md, a[href*='/catalog/']",
                    timeout=15000,
                )
            except Exception:
                logger.warning("[Olcha] Product cards not found")
                return listings

            await page.wait_for_timeout(2000)
            raw_items: list[dict[str, Any]] = await page.evaluate(_EXTRACTION_JS)

            for item in raw_items[: settings.MAX_RESULTS_PER_SITE]:
                title: str = item.get("title", "").strip()
                href: str = item.get("href", "").strip()
                if not title or not href:
                    continue
                if href.startswith("/"):
                    href = _BASE_URL + href

                listings.append(
                    ProductListing(
                        title=title,
                        price=self._parse_price(item.get("price_str", "")),
                        price_str=item.get("price_str", ""),
                        url=href,
                        image_url=item.get("img") or None,
                        marketplace=self.marketplace,
                    )
                )

            logger.info("[Olcha] Extracted %d listings", len(listings))

        except ExtractionError:
            raise
        except Exception as exc:
            logger.error("[Olcha] Unexpected scrape error: %s", exc)
        finally:
            await page.close()
            await ctx.close()

        return listings

    @staticmethod
    def _parse_price(price_str: str) -> Optional[int]:
        clean: str = price_str.split("x")[0].split("\u00d7")[0]
        digits: str = re.sub(r"[^\d]", "", clean)
        return int(digits) if digits else None
