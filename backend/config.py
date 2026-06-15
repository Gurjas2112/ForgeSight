"""
ForgeSight — runtime configuration (pydantic-settings, loaded from .env).
Single source of truth for env-driven behaviour: model backend, Ollama, DB, flags.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- models ---
    model_backend: Literal["slm_only", "hybrid"] = "slm_only"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    embed_model: str = "nomic-embed-text"
    hosted_llm_api_key: str = ""

    # --- synthesis backend (on-prem Ollama by default; hosted API for cloud deploy) ---
    # "ollama" -> local Qwen via Ollama (default, on-prem). "hosted" -> LLM_PROVIDER API
    # (Groq or OpenAI on Railway where Ollama isn't reachable). Set SYNTHESIS_BACKEND=hosted.
    synthesis_backend: Literal["ollama", "hosted"] = "ollama"
    llm_provider: Literal["openai", "groq"] = "groq"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_base_url: str = ""   # auto: groq → https://api.groq.com/openai/v1
    llm_api_key: str = ""

    def hosted_llm_base_url(self) -> str | None:
        """OpenAI-compatible base URL for the configured hosted provider."""
        if self.llm_base_url:
            return self.llm_base_url
        if self.llm_provider == "groq":
            return "https://api.groq.com/openai/v1"
        return None

    # --- retrieval (hybrid vector+full-text locally; full-text-only when no cloud embeddings) ---
    retrieval_mode: Literal["hybrid", "fulltext"] = "hybrid"

    # --- CORS (CSV of allowed frontend origins) ---
    allowed_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,https://forge-sight-one.vercel.app"
    )

    # --- database / supabase ---
    database_url: str = ""                       # postgresql://... (Supabase pooler URI)
    supabase_url: str = Field(
        default="", validation_alias=AliasChoices("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL")
    )
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # --- flags ---
    # DEMO_MODE: when true, scripted golden queries short-circuit the governed graph. Default
    # FALSE so /chat runs the REAL pipeline (the golden card is only an error/timeout fallback).
    demo_mode: bool = False

    # --- alert scheduler (FR-7) — background re-scan of equipment health into alerts ---
    enable_scheduler: bool = False
    scheduler_interval_seconds: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()
