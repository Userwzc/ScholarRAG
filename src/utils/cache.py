import hashlib
import json
import time
from copy import deepcopy
from dataclasses import dataclass
from threading import Lock
from typing import Any

import tiktoken


_TOKENIZER_CACHE: dict[str, Any] = {}
_TOKENIZER_LOCK = Lock()


def get_tokenizer(name: str = "cl100k_base") -> Any:
    tokenizer = _TOKENIZER_CACHE.get(name)
    if tokenizer is not None:
        return tokenizer
    with _TOKENIZER_LOCK:
        tokenizer = _TOKENIZER_CACHE.get(name)
        if tokenizer is None:
            tokenizer = tiktoken.get_encoding(name)
            _TOKENIZER_CACHE[name] = tokenizer
    return tokenizer


def clear_tokenizer_cache() -> None:
    with _TOKENIZER_LOCK:
        _TOKENIZER_CACHE.clear()


@dataclass(slots=True)
class _CacheEntry:
    value: list[dict[str, Any]]
    expires_at: float


class QueryCache:
    def __init__(self, ttl: int = 300) -> None:
        self.ttl = ttl
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = Lock()

    def _key(self, query: str, filters: dict[str, Any]) -> str:
        encoded_filters = json.dumps(filters, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(f"{query}{encoded_filters}".encode("utf-8")).hexdigest()

    def get(self, query: str, filters: dict[str, Any]) -> list[dict[str, Any]] | None:
        key = self._key(query, filters)
        now = time.time()
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._cache.pop(key, None)
                return None
            return deepcopy(entry.value)

    def set(
        self, query: str, filters: dict[str, Any], results: list[dict[str, Any]]
    ) -> None:
        key = self._key(query, filters)
        expires_at = time.time() + max(0, self.ttl)
        with self._lock:
            self._cache[key] = _CacheEntry(
                value=deepcopy(results), expires_at=expires_at
            )

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
