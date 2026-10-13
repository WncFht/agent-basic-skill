"""Shared HTTP timeout and retry policy for paper-search connectors.

``PAPER_SEARCH_TIMEOUT_SECONDS`` is a socket read-idle timeout, not a wall-clock
budget for a whole source.  A response may take longer than this overall as
long as the peer keeps delivering bytes.  ``PAPER_SEARCH_CONNECT_TIMEOUT_SECONDS``
bounds connection establishment separately. The parent process enforces
``PAPER_SEARCH_SOURCE_BUDGET_SECONDS`` across the complete source worker.
"""

from __future__ import annotations

import functools
import math
import os
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_CONNECT_TIMEOUT_SECONDS = 15.0
DEFAULT_READ_TIMEOUT_SECONDS = 300.0
DEFAULT_SOURCE_BUDGET_SECONDS = 180.0
DEFAULT_SOURCE_BUDGET_OVERRIDES = {"openreview": 600.0}
DEFAULT_MAX_ATTEMPTS = 4
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class HTTPConfig:
    connect_timeout: float
    read_timeout: float
    max_attempts: int

    @property
    def timeout(self) -> tuple[float, float]:
        return (self.connect_timeout, self.read_timeout)


def _positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be a positive number of seconds, got {raw!r}"
        ) from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(
            f"{name} must be a positive finite number of seconds, got {raw!r}"
        )
    return value


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}")
    return value


def source_timeout_env(source: str) -> str:
    return f"PAPER_SEARCH_{source.upper()}_TIMEOUT_SECONDS"


def source_budget_env(source: str) -> str:
    return f"PAPER_SEARCH_{source.upper()}_BUDGET_SECONDS"


def get_source_budget(source: str) -> float:
    global_budget = _positive_float(
        "PAPER_SEARCH_SOURCE_BUDGET_SECONDS",
        DEFAULT_SOURCE_BUDGET_OVERRIDES.get(source, DEFAULT_SOURCE_BUDGET_SECONDS),
    )
    return _positive_float(source_budget_env(source), global_budget)


def get_http_config(source: str) -> HTTPConfig:
    """Resolve global and per-source settings from the current environment."""
    global_read = _positive_float(
        "PAPER_SEARCH_TIMEOUT_SECONDS", DEFAULT_READ_TIMEOUT_SECONDS
    )
    read_timeout = _positive_float(source_timeout_env(source), global_read)
    connect_timeout = _positive_float(
        "PAPER_SEARCH_CONNECT_TIMEOUT_SECONDS", DEFAULT_CONNECT_TIMEOUT_SECONDS
    )
    max_attempts = _positive_int("PAPER_SEARCH_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)
    return HTTPConfig(connect_timeout, read_timeout, max_attempts)


def validate_environment(sources: Iterable[str]) -> None:
    """Fail before spawning workers when any selected timeout setting is invalid."""
    for source in sources:
        get_http_config(source)
        get_source_budget(source)


def create_session(user_agent: str | None = None) -> requests.Session:
    """Create a plain session; retries are applied explicitly by ``request``."""
    session = requests.Session()
    if user_agent:
        session.headers["User-Agent"] = user_agent
    return session


def polite_user_agent(service: str = "PaperSearch/1.0") -> str:
    """Build a User-Agent with the contact address, when one is configured.

    Crossref and DBLP ask for an identifiable agent with a contact address;
    anonymous-looking clients see more rate limiting and dropped connections.
    """
    contact = os.environ.get("PAPER_SEARCH_CONTACT_EMAIL", "").strip()
    return f"{service} (mailto:{contact})" if contact else service


def _retry_after_seconds(response: requests.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw)
            if retry_at.tzinfo is None:
                return None
            return max(0.0, retry_at.timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return None


def _retry_delay(
    response: requests.Response, attempt: int, cap: float, backoff_base: float = 3.0
) -> float:
    retry_after = _retry_after_seconds(response)
    delay = (
        retry_after if retry_after is not None else backoff_base * (2 ** (attempt - 1))
    )
    return min(cap, max(0.0, delay))


def request(
    session: requests.Session,
    method: str,
    url: str,
    *,
    source: str,
    before_attempt: Callable[[], None] | None = None,
    backoff_base: float = 3.0,
    **kwargs,
) -> requests.Response:
    """Issue one HTTP request with bounded status retries and socket timeouts.

    Network exceptions are surfaced immediately.  Only explicit transient HTTP
    statuses are retried, so a permanently rate-limited endpoint cannot loop
    forever.  ``backoff_base`` sets the exponential delay seed for endpoints
    that need more politeness than the default 3/6/12s ladder.
    """
    config = get_http_config(source)
    # Connectors share one public timeout contract; a local call site cannot
    # accidentally reintroduce an unbounded or single-value timeout.
    kwargs["timeout"] = config.timeout

    for attempt in range(1, config.max_attempts + 1):
        if before_attempt is not None:
            before_attempt()
        try:
            response = session.request(method, url, **kwargs)
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as exc:
            if (
                method.upper() not in IDEMPOTENT_METHODS
                or attempt >= config.max_attempts
            ):
                raise
            delay = min(config.read_timeout, backoff_base * (2 ** (attempt - 1)))
            print(
                f"[{source}] {type(exc).__name__}; retrying in {delay:g}s "
                f"(attempt {attempt + 1}/{config.max_attempts})",
                file=sys.stderr,
            )
            time.sleep(delay)
            continue
        if response.status_code not in RETRYABLE_STATUS_CODES:
            return response
        if attempt >= config.max_attempts:
            return response

        delay = _retry_delay(response, attempt, config.read_timeout, backoff_base)
        print(
            f"[{source}] HTTP {response.status_code}; retrying in {delay:g}s "
            f"(attempt {attempt + 1}/{config.max_attempts})",
            file=sys.stderr,
        )
        response.close()
        time.sleep(delay)

    raise RuntimeError("unreachable")


def configure_external_session(
    session: requests.Session, source: str
) -> requests.Session:
    """Install paper-search defaults on a requests Session owned by a dependency.

    OpenReview constructs its own Session and does not expose a timeout argument.
    Re-mounting a bounded adapter and wrapping ``Session.request`` applies the same
    policy to authentication plus every paginated v1/v2 request.
    """
    config = get_http_config(source)
    retry = Retry(
        total=config.max_attempts - 1,
        connect=config.max_attempts - 1,
        read=0,
        status=config.max_attempts - 1,
        backoff_factor=1.5,
        status_forcelist=sorted(RETRYABLE_STATUS_CODES),
        allowed_methods=IDEMPOTENT_METHODS,
        redirect=0,
        other=0,
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    original_request = session.request

    @functools.wraps(original_request)
    def request_with_default_timeout(method, url, **kwargs):
        kwargs["timeout"] = config.timeout
        return original_request(method, url, **kwargs)

    session.request = request_with_default_timeout  # type: ignore[assignment,method-assign]
    return session
