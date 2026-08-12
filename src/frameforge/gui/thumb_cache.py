"""Bounded LRU cache for decoded queue thumbnails."""

from __future__ import annotations

from collections import OrderedDict
from typing import Generic, TypeVar

T = TypeVar("T")

THUMB_CACHE_MAX = 64


class LruCache(Generic[T]):
    """Insertion/access-ordered cache that evicts the least recently used key."""

    def __init__(self, maxsize: int = THUMB_CACHE_MAX) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self.maxsize = maxsize
        self._data: OrderedDict[str, T] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> T | None:
        if key in self._data:
            self._data.move_to_end(key)
            self.hits += 1
            return self._data[key]
        self.misses += 1
        return None

    def put(self, key: str, value: T) -> None:
        if key in self._data:
            self._data.move_to_end(key)
            self._data[key] = value
            return
        self._data[key] = value
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)
