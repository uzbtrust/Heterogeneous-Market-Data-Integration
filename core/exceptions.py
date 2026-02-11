from __future__ import annotations

from typing import Any, Optional


class AppException(Exception):

    def __init__(
        self,
        message: str,
        *,
        detail: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message: str = message
        self.detail: Optional[str] = detail
        self.context: dict[str, Any] = context or {}
        super().__init__(self.message)

    def __repr__(self) -> str:
        cls: str = self.__class__.__name__
        parts: list[str] = [f"{cls}('{self.message}')"]
        if self.detail:
            parts.append(f"detail='{self.detail}'")
        if self.context:
            parts.append(f"context={self.context}")
        return " | ".join(parts)


# ── Scraper layer ──────────────────────────────────────────────

class ScraperException(AppException):
    pass


class NavigationError(ScraperException):
    pass


class ExtractionError(ScraperException):
    pass


class MarketplaceUnavailable(ScraperException):
    pass


# ── Reasoning layer ────────────────────────────────────────────

class ReasoningException(AppException):
    pass


class LLMConnectionError(ReasoningException):
    pass


class LLMResponseError(ReasoningException):
    pass


class QueryParseError(ReasoningException):
    pass


# ── Pipeline layer ─────────────────────────────────────────────

class PipelineException(AppException):
    pass


class WorkerError(PipelineException):
    pass


class OrchestratorError(PipelineException):
    pass
