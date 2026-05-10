from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path


class JsonCache:
    def __init__(self, path: str, ttl_seconds: int):
        self.path = Path(path)
        self.ttl_seconds = int(ttl_seconds)
        self._lock = threading.Lock()

    @staticmethod
    def key(value: str) -> str:
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

    def _load(self) -> dict:
        try:
            if self.path.exists():
                with self.path.open(encoding="utf-8") as cache_file:
                    loaded = json.load(cache_file)
                if isinstance(loaded, dict):
                    return loaded
        except (OSError, json.JSONDecodeError):
            return {}
        return {}

    def _save(self, cache: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as cache_file:
            json.dump(cache, cache_file, ensure_ascii=False)
        os.replace(temp_path, self.path)

    def get(self, value: str) -> str:
        now = time.time()
        key = self.key(value)
        with self._lock:
            item = self._load().get(key)
        if isinstance(item, dict) and now - float(item.get("created_at", 0)) <= self.ttl_seconds:
            description = item.get("description")
            return description if isinstance(description, str) else ""
        return ""

    def set(self, value: str, description: str) -> None:
        key = self.key(value)
        with self._lock:
            cache = self._load()
            cache[key] = {"created_at": time.time(), "description": description}
            self._save(cache)
