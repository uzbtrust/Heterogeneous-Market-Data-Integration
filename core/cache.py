from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

import aioredis
from aioredis.exceptions import RedisError

from core.config import settings
from core.models import ProductListing

logger: logging.Logger = logging.getLogger(__name__)

_CACHE_PREFIX: str = "query_cache:"


def get_cache_key(query: str) -> str:
    """SHA-256 hash of the query string, prefixed for namespace isolation."""
    digest: str = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"{_CACHE_PREFIX}{digest}"


async def get_from_cache(query: str) -> Optional[list[ProductListing]]:
    """
    Try to fetch aggregated raw listings from Redis.
    Returns a list of ProductListing on cache hit, None on miss or any error.
    Errors are handled silently so the caller can fall back to live scraping.
    """
    key: str = get_cache_key(query)
    redis: Optional[aioredis.Redis] = None
    try:
        redis = await aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        raw: Optional[str] = await redis.get(key)
        if raw is None:
            return None

        data: list[dict] = json.loads(raw)
        listings: list[ProductListing] = [
            ProductListing.model_validate(item) for item in data
        ]
        return listings

    except RedisError as exc:
        logger.warning("[Cache] Redis error during GET: %s", exc)
        return None
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("[Cache] Deserialization error: %s", exc)
        return None
    finally:
        if redis is not None:
            await redis.aclose()


async def set_to_cache(query: str, listings: list[ProductListing]) -> None:
    """
    Persist aggregated raw listings to Redis with TTL = CACHE_TTL_SECONDS.
    Errors are handled silently — caching is best-effort.
    """
    key: str = get_cache_key(query)
    redis: Optional[aioredis.Redis] = None
    try:
        redis = await aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        payload: str = json.dumps(
            [listing.model_dump(mode="json") for listing in listings],
            ensure_ascii=False,
        )
        await redis.set(key, payload, ex=settings.CACHE_TTL_SECONDS)

    except RedisError as exc:
        logger.warning("[Cache] Redis error during SET: %s", exc)
    except Exception as exc:
        logger.warning("[Cache] Serialization error: %s", exc)
    finally:
        if redis is not None:
            await redis.aclose()
