"""
ForgeSight — cache lookup chain (cache_lookup node).
Full design chain (§1.8): demo_cache → semantic_cache (≥0.95, knowledge-class ONLY) → TTL → …
Pass 1 ships the top of the chain: a demo_cache for scripted queries (so a live failure never
shows a spinner-of-death) and a NULL semantic layer. Live-status is NEVER cached (stale RUL is
dangerous) — enforced by only caching query_class == 'knowledge'.
"""

from __future__ import annotations

from typing import Any


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


class CacheChain:
    def __init__(self, demo_cache: dict[str, dict] | None = None, demo_mode: bool = True):
        # demo_cache key = normalized "<equipment_id>::<query>"
        self.demo = demo_cache or {}
        self.demo_mode = demo_mode
        self._semantic: dict[str, dict] = {}        # in-memory stand-in for semantic_cache

    def lookup(self, text: str, equipment_id: str | None, query_class: str | None) -> dict | None:
        key = f"{equipment_id or ''}::{_norm(text)}"
        if self.demo_mode and key in self.demo:
            return self.demo[key]
        if query_class == "knowledge" and key in self._semantic:
            return self._semantic[key]
        return None                                   # miss → run the graph

    def store(self, text: str, equipment_id: str | None, card: dict) -> None:
        # knowledge-class only (the respond node already guards on query_class + not degraded)
        self._semantic[f"{equipment_id or ''}::{_norm(text)}"] = card
