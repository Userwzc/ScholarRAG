from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.utils.exceptions import ExternalServiceError

T = TypeVar("T")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(ExternalServiceError),
    reraise=True,
)
def call_with_circuit_breaker(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    try:
        return fn(*args, **kwargs)
    except ExternalServiceError:
        raise
    except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
        raise ExternalServiceError("External service call failed", log_message=str(exc))
