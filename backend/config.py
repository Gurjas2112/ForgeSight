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

    # --- database / supabase ---
    database_url: str = ""                       # postgresql://... (Supabase pooler URI)
    supabase_url: str = Field(
        default="", validation_alias=AliasChoices("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL")
    )
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # --- flags ---
    demo_mode: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
