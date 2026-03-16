"""Response caching layer for LLM API calls."""

import hashlib
import json
import os


class LLMCache:
    """File-based cache for LLM responses. One JSON file per cache key."""

    def __init__(self, cache_dir: str = ".fabric-ai-meta-cache"):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def make_key(self, prompt: str) -> str:
        """Generate a SHA-256 hash key from the prompt string."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def get(self, key: str) -> str | None:
        """Return cached response for key, or None on cache miss."""
        path = os.path.join(self.cache_dir, key)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("response")

    def set(self, key: str, response: str) -> None:
        """Store a response in the cache."""
        path = os.path.join(self.cache_dir, key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"response": response}, f)
