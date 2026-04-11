"""LRU cache for Bedrock responses.

Simple OrderedDict-based LRU cache to avoid repeated API calls
for the same keystroke patterns.
"""

from collections import OrderedDict


class LRUCache:
    """Least Recently Used cache with max size."""

    def __init__(self, max_size: int = 256):
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> str | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, value: str) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
        self._cache[key] = value

    def __len__(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        self._cache.clear()
