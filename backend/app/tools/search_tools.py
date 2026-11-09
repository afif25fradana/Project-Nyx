import os
import time
from typing import Any


class SearchClient:
    """Tavily search client with DDGS fallback and in-memory 1-hour TTL cache (AC-7)."""

    def __init__(
        self,
        api_key: str | None = None,
        ttl_seconds: float = 3600.0,
        tavily_client: Any = None,
        ddgs_client: Any = None,
        max_cache_size: int = 256,
    ) -> None:
        self._api_key = api_key or os.environ.get("TAVILY_API_KEY")
        self._ttl = ttl_seconds
        self._tavily = tavily_client
        self._ddgs = ddgs_client
        self._max_cache_size = max_cache_size
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def _set_cache(self, cache_key: str, results: list[dict[str, Any]], now: float) -> None:
        """Store results in cache, pruning expired or oldest entries if capacity is reached."""
        if len(self._cache) >= self._max_cache_size and cache_key not in self._cache:
            expired_keys = [k for k, (ts, _) in self._cache.items() if (now - ts) >= self._ttl]
            for k in expired_keys:
                del self._cache[k]
            while len(self._cache) >= self._max_cache_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]
        self._cache[cache_key] = (now, results)

    def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Search the web with cache check -> Tavily primary -> DDGS fallback."""
        if not query or not query.strip():
            return []

        clean_query = query.strip()
        cache_key = clean_query.lower()
        now = time.time()

        # Cache Hit Check (3600s TTL)
        if cache_key in self._cache:
            timestamp, cached_results = self._cache[cache_key]
            if (now - timestamp) < self._ttl:
                return cached_results

        # 1. Primary: Tavily Search
        if self._tavily is None and self._api_key:
            try:
                from tavily import TavilyClient

                self._tavily = TavilyClient(api_key=self._api_key)
            except Exception:
                self._tavily = None

        if self._tavily is not None:
            try:
                raw_response = self._tavily.search(query=clean_query, max_results=max_results)
                raw_items = raw_response.get("results", []) if isinstance(raw_response, dict) else []
                results: list[dict[str, Any]] = []
                for item in raw_items:
                    snippet = item.get("content", "")
                    results.append(
                        {
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "snippet": snippet,
                            "content": snippet,
                        }
                    )
                self._set_cache(cache_key, results, now)
                return results
            except Exception:
                pass  # Fall through to DDGS fallback

        # 2. Fallback: DuckDuckGo Search (ddgs)
        try:
            if self._ddgs is None:
                try:
                    from ddgs import DDGS
                except ImportError:
                    from duckduckgo_search import DDGS

                self._ddgs = DDGS()

            raw_items = list(self._ddgs.text(clean_query, max_results=max_results))
            results: list[dict[str, Any]] = []
            for item in raw_items:
                snippet = item.get("body", "")
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("href", ""),
                        "snippet": snippet,
                        "content": snippet,
                    }
                )
            self._set_cache(cache_key, results, now)
            return results
        except Exception:
            # Avoid negative caching on failure
            return []

    def clear_cache(self) -> None:
        """Clear all in-memory search cache entries."""
        self._cache.clear()
