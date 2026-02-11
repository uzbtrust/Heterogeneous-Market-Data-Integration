from __future__ import annotations

import abc
import logging
from types import TracebackType
from typing import Any, Optional, Self

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response,
    async_playwright,
)

from core.config import settings
from core.exceptions import MarketplaceUnavailable, NavigationError
from core.models import Marketplace, ProductListing

logger: logging.Logger = logging.getLogger(__name__)


class BaseScraper(abc.ABC):

    marketplace: Marketplace

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "__abstractmethods__", None):
            if not hasattr(cls, "marketplace") or not isinstance(
                cls.__dict__.get("marketplace"), Marketplace
            ):
                raise TypeError(
                    f"{cls.__name__} must define a class-level "
                    f"'marketplace' attribute of type Marketplace"
                )

    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

    async def __aenter__(self) -> Self:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=settings.HEADLESS,
        )
        logger.debug(
            "[%s] Browser launched (headless=%s)",
            self.marketplace.value, settings.HEADLESS,
        )
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.debug("[%s] Browser closed", self.marketplace.value)

    async def _new_context(self) -> BrowserContext:
        if self._browser is None:
            raise MarketplaceUnavailable(
                "Browser not initialized — use 'async with' context manager",
                context={"marketplace": self.marketplace.value},
            )
        return await self._browser.new_context(
            user_agent=settings.USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="uz-UZ",
        )

    async def _safe_goto(self, page: Page, url: str) -> bool:
        try:
            resp: Optional[Response] = await page.goto(
                url,
                timeout=settings.SCRAPE_TIMEOUT_MS,
                wait_until="domcontentloaded",
            )
            if resp and resp.status >= 400:
                logger.warning(
                    "[%s] HTTP %d for %s",
                    self.marketplace.value, resp.status, url,
                )
                return False
            return True
        except Exception as exc:
            logger.error(
                "[%s] Navigation failed for %s: %s",
                self.marketplace.value, url, exc,
            )
            raise NavigationError(
                f"Navigation to {url} failed",
                detail=str(exc),
                context={"marketplace": self.marketplace.value, "url": url},
            ) from exc

    @abc.abstractmethod
    async def scrape(self, query: str) -> list[ProductListing]:
        ...
