"""
scheduler/pipeline/resilience.py  — Security Patch #7

Circuit breakers and exponential backoff for all external AI/scraping calls.

Circuit breaker states:
  closed  → service is healthy, calls go through
  open    → too many failures, calls are blocked (return fallback immediately)
  half-open → recovery probe after timeout, one call allowed through

Module-level breakers are shared across all calls within a single scheduler run.
They reset (to closed) on the next process start (each GitHub Actions run).
"""

import logging
import time

logger = logging.getLogger("jobpulse.scheduler")


class CircuitBreaker:
    """
    Simple circuit breaker — no Redis, no persistence.
    Resets to closed on every process restart (per GitHub Actions run).
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 300,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._opened_at: float | None = None
        self._state = "closed"  # closed | open | half-open

    @property
    def is_open(self) -> bool:
        if self._state == "open":
            if (
                self._opened_at is not None
                and time.time() - self._opened_at > self.recovery_timeout
            ):
                self._state = "half-open"
                logger.info(
                    '{"event": "circuit_breaker_half_open", "breaker": "%s"}',
                    self.name,
                )
                return False
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._state = "open"
            self._opened_at = time.time()
            logger.error(
                '{"event": "circuit_breaker_opened", "breaker": "%s", "failures": %d}',
                self.name,
                self._failures,
            )

    def call_with_fallback(self, fn, fallback, *args, max_retries: int = 3, **kwargs):
        """
        Execute fn(*args, **kwargs) with exponential backoff retries.
        Returns fallback if circuit is open or all retries exhausted.
        """
        if self.is_open:
            logger.warning(
                '{"event": "circuit_breaker_blocked", "breaker": "%s"}',
                self.name,
            )
            return fallback

        for attempt in range(1, max_retries + 1):
            try:
                result = fn(*args, **kwargs)
                self.record_success()
                return result
            except Exception as e:
                self.record_failure()
                if attempt == max_retries:
                    logger.error(
                        '{"event": "max_retries_exceeded", "breaker": "%s", "error": "%s"}',
                        self.name,
                        str(e),
                    )
                    return fallback
                sleep_time = 2**attempt  # 2s, 4s, 8s
                logger.warning(
                    '{"event": "retry_backoff", "breaker": "%s", "attempt": %d, "sleep": %d}',
                    self.name,
                    attempt,
                    sleep_time,
                )
                time.sleep(sleep_time)

        return fallback


# Module-level circuit breakers — one per external service
groq_breaker = CircuitBreaker("groq", failure_threshold=5, recovery_timeout=300)
gemini_breaker = CircuitBreaker("gemini", failure_threshold=5, recovery_timeout=300)
jina_breaker = CircuitBreaker("jina", failure_threshold=10, recovery_timeout=120)
