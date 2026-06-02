"""NewsAPI scraper implementation."""

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import List

import httpx

from .base import BaseScraper
from ..models import ContentItem, NewsAPIConfig, SourceType

logger = logging.getLogger(__name__)

_BASE_URL = "https://newsapi.org/v2/top-headlines"


class NewsAPIScraper(BaseScraper):
    """Scraper for NewsAPI top headlines."""

    def __init__(self, config: NewsAPIConfig, http_client: httpx.AsyncClient):
        super().__init__({"config": config}, http_client)
        self.cfg = config

    async def fetch(self, since: datetime) -> List[ContentItem]:
        api_key = os.environ.get(self.cfg.api_key_env, "").strip()
        if not api_key:
            logger.warning("NewsAPI key not set (%s), skipping", self.cfg.api_key_env)
            return []

        items: List[ContentItem] = []
        for category in self.cfg.categories:
            try:
                fetched = await self._fetch_category(api_key, category, since)
                items.extend(fetched)
            except Exception as exc:
                logger.warning("NewsAPI error for category '%s': %s", category, exc)

        return items

    async def _fetch_category(
        self, api_key: str, category: str, since: datetime
    ) -> List[ContentItem]:
        # Use /everything with explicit date range so recent articles aren't
        # filtered out — top-headlines often returns articles published before
        # the `since` window.
        from_date = since.strftime("%Y-%m-%dT%H:%M:%S")
        params = {
            "q": category,
            "language": self.cfg.language,
            "pageSize": str(self.cfg.page_size),
            "sortBy": "publishedAt",
            "from": from_date,
            "apiKey": api_key,
        }
        url = "https://newsapi.org/v2/everything"
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        articles = response.json().get("articles", [])

        items = []
        for article in articles:
            published_str = article.get("publishedAt", "")
            try:
                published_at = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                published_at = datetime.now(timezone.utc)

            url = article.get("url") or ""
            if not url:
                continue

            url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
            source_name = (article.get("source") or {}).get("name", "NewsAPI")

            items.append(
                ContentItem(
                    id=self._generate_id("newsapi", category, url_hash),
                    source_type=SourceType.NEWSAPI,
                    title=article.get("title") or "Untitled",
                    url=url,
                    content=article.get("description") or article.get("content") or "",
                    author=article.get("author") or source_name,
                    published_at=published_at,
                    metadata={"category": category, "source_name": source_name},
                )
            )

        return items
