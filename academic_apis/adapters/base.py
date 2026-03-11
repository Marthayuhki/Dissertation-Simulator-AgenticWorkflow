"""Base adapter interface for all academic database APIs."""

from __future__ import annotations

import logging
import random
import threading
import time
from abc import ABC, abstractmethod

import requests

from academic_apis.config import APIConfig
from academic_apis.models import Paper

logger = logging.getLogger(__name__)

# Browser User-Agent pool for anti-blocking rotation
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 OPR/109.0.0.0",
]

# Retryable HTTP status codes
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class BaseAdapter(ABC):
    """Abstract base for all academic database adapters.

    Provides:
    - Thread-safe rate limiting
    - Resilient HTTP requests with exponential backoff + jitter
    - User-Agent rotation for anti-blocking
    - Automatic retry on transient failures (429, 5xx)
    - Session cleanup
    """

    name: str = "base"

    def __init__(self, config: APIConfig) -> None:
        self.config = config
        self._last_request_time: float = 0.0
        self._rate_lock = threading.Lock()
        self._session = requests.Session()
        self._session.headers["User-Agent"] = random.choice(_USER_AGENTS)

    @abstractmethod
    def search(
        self,
        query: str,
        *,
        max_results: int = 50,
        year_from: int | None = None,
        year_to: int | None = None,
        sort_by: str = "relevance",
    ) -> list[Paper]:
        """Search for papers matching the query."""

    @abstractmethod
    def get_paper(self, identifier: str) -> Paper | None:
        """Get a single paper by DOI or database-specific ID."""

    def get_citations(self, identifier: str, max_results: int = 50) -> list[Paper]:
        """Get papers that cite the given work. Override in subclass if supported."""
        return []

    def get_references(self, identifier: str, max_results: int = 50) -> list[Paper]:
        """Get papers referenced by the given work. Override in subclass if supported."""
        return []

    def is_available(self) -> bool:
        """Check if this adapter is configured and ready to use."""
        return True

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()

    def _rate_limit(self, min_interval: float) -> None:
        """Enforce minimum interval between requests (thread-safe)."""
        with self._rate_lock:
            elapsed = time.time() - self._last_request_time
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self._last_request_time = time.time()

    def _rotate_user_agent(self) -> None:
        """Rotate to a different User-Agent string."""
        self._session.headers["User-Agent"] = random.choice(_USER_AGENTS)

    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        rate_limit_interval: float = 0.0,
        **kwargs,
    ) -> requests.Response:
        """Execute an HTTP request with exponential backoff, jitter, and UA rotation.

        Args:
            method: HTTP method ("GET", "POST", etc.)
            url: Request URL.
            max_retries: Maximum retry attempts (default 5).
            base_delay: Initial backoff delay in seconds.
            max_delay: Maximum backoff delay cap.
            rate_limit_interval: If >0, apply rate limiting before request.
            **kwargs: Passed to requests.Session.request() (params, timeout, etc.)

        Returns:
            requests.Response on success.

        Raises:
            requests.HTTPError: After all retries exhausted.
            requests.ConnectionError: After all retries exhausted.
            requests.Timeout: After all retries exhausted.
        """
        if rate_limit_interval > 0:
            self._rate_limit(rate_limit_interval)

        # Default timeout if not specified
        kwargs.setdefault("timeout", 30)

        last_exc: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                resp = self._session.request(method, url, **kwargs)

                # Success — return immediately
                if resp.status_code < 400:
                    return resp

                # 403 Forbidden — likely UA blocking, rotate and retry
                if resp.status_code == 403:
                    self._rotate_user_agent()
                    if attempt < max_retries:
                        delay = self._backoff_delay(attempt, base_delay, max_delay)
                        logger.warning(
                            "%s: 403 from %s, rotating UA, retry in %.1fs (attempt %d/%d)",
                            self.name, url, delay, attempt + 1, max_retries,
                        )
                        time.sleep(delay)
                        continue
                    resp.raise_for_status()

                # 429 Too Many Requests — respect Retry-After header
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = min(float(retry_after), max_delay)
                        except ValueError:
                            delay = self._backoff_delay(attempt, base_delay, max_delay)
                    else:
                        delay = self._backoff_delay(attempt, base_delay, max_delay)

                    if attempt < max_retries:
                        logger.warning(
                            "%s: 429 from %s, retry in %.1fs (attempt %d/%d)",
                            self.name, url, delay, attempt + 1, max_retries,
                        )
                        time.sleep(delay)
                        continue
                    resp.raise_for_status()

                # Other retryable server errors (500, 502, 503, 504)
                if resp.status_code in _RETRYABLE_STATUS:
                    if attempt < max_retries:
                        delay = self._backoff_delay(attempt, base_delay, max_delay)
                        logger.warning(
                            "%s: %d from %s, retry in %.1fs (attempt %d/%d)",
                            self.name, resp.status_code, url, delay, attempt + 1, max_retries,
                        )
                        time.sleep(delay)
                        continue
                    resp.raise_for_status()

                # Non-retryable client error (400, 404, 422, etc.) — fail immediately
                resp.raise_for_status()

            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                if attempt < max_retries:
                    self._rotate_user_agent()
                    delay = self._backoff_delay(attempt, base_delay, max_delay)
                    logger.warning(
                        "%s: %s for %s, retry in %.1fs (attempt %d/%d)",
                        self.name, type(e).__name__, url, delay, attempt + 1, max_retries,
                    )
                    time.sleep(delay)
                    continue
                raise

            except requests.HTTPError:
                # Already raised by raise_for_status() above after max retries
                raise

        # Should not reach here, but safety net
        if last_exc:
            raise last_exc
        raise requests.HTTPError(f"{self.name}: request failed after {max_retries} retries")

    @staticmethod
    def _backoff_delay(attempt: int, base: float, cap: float) -> float:
        """Exponential backoff with full jitter: uniform(0, min(cap, base * 2^attempt))."""
        exp = min(cap, base * (2 ** attempt))
        return random.uniform(0, exp)
