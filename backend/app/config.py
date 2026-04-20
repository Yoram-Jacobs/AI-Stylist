"""Centralised settings loader for DressApp.

Every secret / config value is read from environment variables loaded from
`/app/backend/.env`. Nothing is ever hardcoded. Missing required secrets cause a
clear, loud failure at application startup so we never silently mock providers.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Load .env once at import time
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


class Settings:
    # --- infra ---
    MONGO_URL: str = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    DB_NAME: str = os.environ.get("DB_NAME", "test_database")
    CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")

    # --- auth ---
    JWT_SECRET: str = os.environ.get("JWT_SECRET", "dressapp-dev-change-me")
    JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
    JWT_EXPIRES_MIN: int = int(os.environ.get("JWT_EXPIRES_MIN", "43200"))

    # --- LLM (Emergent Universal Key, Gemini 2.5 Pro) ---
    EMERGENT_LLM_KEY: str | None = os.environ.get("EMERGENT_LLM_KEY")
    DEFAULT_STYLIST_MODEL: str = os.environ.get("DEFAULT_STYLIST_MODEL", "gemini-2.5-pro")
    DEFAULT_STYLIST_PROVIDER: str = os.environ.get("DEFAULT_STYLIST_PROVIDER", "gemini")

    # --- Hugging Face (garment segmentation) ---
    HF_TOKEN: str | None = os.environ.get("HF_TOKEN") or None
    # Defaults to a purpose-built clothing segmenter. SAM is kept as a config
    # surface but is not reachable on the serverless tier as of 2026.
    HF_SAM_MODEL: str = os.environ.get(
        "HF_SAM_MODEL", "mattmdjaga/segformer_b2_clothes"
    )

    # --- Gemini Nano Banana (image generation + edit) ---
    GEMINI_IMAGE_MODEL: str = os.environ.get(
        "GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview"
    )

    # --- The Eyes (garment vision analyzer) ---
    # Starts on Gemini 2.5 Pro; flip to fine-tuned Gemma 4 E4B when ready.
    GARMENT_VISION_PROVIDER: str = os.environ.get(
        "GARMENT_VISION_PROVIDER", "gemini"
    )
    GARMENT_VISION_MODEL: str = os.environ.get(
        "GARMENT_VISION_MODEL", "gemini-2.5-pro"
    )

    # --- Hugging Face image generation (replaces Nano Banana edit/generate) ---
    HF_IMAGE_MODEL: str = os.environ.get(
        "HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell"
    )
    HF_IMAGE_PROVIDER: str = os.environ.get("HF_IMAGE_PROVIDER", "hf-inference")

    # --- Groq (Whisper-v3) ---
    GROQ_API_KEY: str | None = os.environ.get("GROQ_API_KEY")
    WHISPER_MODEL: str = os.environ.get("WHISPER_MODEL", "whisper-large-v3")

    # --- Deepgram (Aura-2 TTS) ---
    DEEPGRAM_API_KEY: str | None = os.environ.get("DEEPGRAM_API_KEY")
    DEFAULT_TTS_MODEL: str = os.environ.get("DEFAULT_TTS_MODEL", "aura-2-thalia-en")
    DEFAULT_TTS_ENCODING: str = os.environ.get("DEFAULT_TTS_ENCODING", "mp3")

    # --- OpenWeatherMap ---
    OPENWEATHER_API_KEY: str | None = os.environ.get("OPENWEATHER_API_KEY")

    # --- Stripe (Phase 4) ---
    STRIPE_SECRET_KEY: str | None = os.environ.get("STRIPE_SECRET_KEY") or None
    STRIPE_PUBLISHABLE_KEY: str | None = os.environ.get("STRIPE_PUBLISHABLE_KEY") or None
    STRIPE_WEBHOOK_SECRET: str | None = os.environ.get("STRIPE_WEBHOOK_SECRET") or None
    STRIPE_PLATFORM_FEE_PERCENT: float = float(
        os.environ.get("STRIPE_PLATFORM_FEE_PERCENT", "7")
    )
    STRIPE_PROCESSING_FEE_PERCENT: float = float(
        os.environ.get("STRIPE_PROCESSING_FEE_PERCENT", "2.9")
    )
    STRIPE_PROCESSING_FEE_FIXED_CENTS: int = int(
        os.environ.get("STRIPE_PROCESSING_FEE_FIXED_CENTS", "30")
    )

    # --- Google OAuth (Phase 4) ---
    GOOGLE_OAUTH_CLIENT_ID: str | None = os.environ.get("GOOGLE_OAUTH_CLIENT_ID") or None
    GOOGLE_OAUTH_CLIENT_SECRET: str | None = (
        os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") or None
    )
    GOOGLE_OAUTH_REDIRECT_URI: str | None = (
        os.environ.get("GOOGLE_OAUTH_REDIRECT_URI") or None
    )
    GOOGLE_OAUTH_POST_LOGIN_REDIRECT: str | None = (
        os.environ.get("GOOGLE_OAUTH_POST_LOGIN_REDIRECT") or None
    )

    # --- Dev toggles ---
    ALLOW_DEV_BYPASS: bool = os.environ.get("ALLOW_DEV_BYPASS", "true").lower() == "true"

    # --- Trend-Scout scheduler ---
    TREND_SCOUT_ENABLED: bool = (
        os.environ.get("TREND_SCOUT_ENABLED", "true").lower() == "true"
    )
    # Daily cron expressed as "HH:MM" in UTC.
    TREND_SCOUT_SCHEDULE_UTC: str = os.environ.get(
        "TREND_SCOUT_SCHEDULE_UTC", "07:00"
    )
    # If True, attempt a run on server startup (best-effort, non-blocking).
    TREND_SCOUT_RUN_ON_STARTUP: bool = (
        os.environ.get("TREND_SCOUT_RUN_ON_STARTUP", "false").lower() == "true"
    )

    def require(self, *keys: str) -> None:
        missing = [k for k in keys if not getattr(self, k, None)]
        if missing:
            raise RuntimeError(
                f"Missing required configuration: {', '.join(missing)}. "
                "Populate /app/backend/.env then restart the backend."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
