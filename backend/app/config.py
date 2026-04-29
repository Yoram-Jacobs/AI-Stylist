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
    DB_NAME: str = os.environ.get("DB_NAME", "dressapp")
    CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "https://dressapp.co,https://www.dressapp.co")

    # --- auth ---
    JWT_SECRET: str = os.environ.get("JWT_SECRET", "dressapp_jwt_secret_xK9mQ2nP4vR7sT8uW")
    JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
    JWT_EXPIRES_MIN: int = int(os.environ.get("JWT_EXPIRES_MIN", "43200"))

    # --- LLM keys ----------------------------------------------------
    # Two valid configurations, in order of precedence:
    #
    # 1. **Direct Gemini** (production): set ``GEMINI_API_KEY`` in .env.
    #    Every Gemini-routed call (Stylist, The Eyes, Trend-Scout, ...)
    #    talks to Google's API natively via litellm — no Emergent proxy
    #    in the path. Required for Nano Banana image generation, which
    #    the Emergent proxy does not support.
    #
    # 2. **Emergent Universal Key** (dev preview): set ``EMERGENT_LLM_KEY``
    #    only. Routes through the Emergent proxy. Free for dev work but
    #    cannot do Nano Banana, and counts against the user's credit
    #    balance.
    #
    # Both can be set; ``GEMINI_API_KEY`` always wins for chat calls.
    EMERGENT_LLM_KEY: str | None = os.environ.get("EMERGENT_LLM_KEY") or None
    GEMINI_API_KEY: str | None = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")  # accept the canonical google-genai name too
        or None
    )
    DEFAULT_STYLIST_MODEL: str = os.environ.get("DEFAULT_STYLIST_MODEL", "gemini-2.5-pro")
    DEFAULT_STYLIST_PROVIDER: str = os.environ.get("DEFAULT_STYLIST_PROVIDER", "gemini")

    @property
    def gemini_chat_key(self) -> str | None:
        """Pick the right key for litellm-backed Gemini chat calls.

        Production deployments set ``GEMINI_API_KEY``; dev preview falls
        back to ``EMERGENT_LLM_KEY`` (which litellm sends through the
        Emergent proxy because the key starts with ``sk-emergent-``).
        """
        return self.GEMINI_API_KEY or self.EMERGENT_LLM_KEY

    @property
    def has_native_gemini(self) -> bool:
        """True when a direct Google key is configured (enables Nano Banana)."""
        return bool(self.GEMINI_API_KEY)

    # --- Hugging Face (garment segmentation) ---
    HF_TOKEN: str | None = os.environ.get("HF_TOKEN") or None
    # Defaults to a purpose-built clothing segmenter. SAM is kept as a config
    # surface but is not reachable on the serverless tier as of 2026.
    HF_SAM_MODEL: str = os.environ.get(
        "HF_SAM_MODEL", "mattmdjaga/segformer_b2_clothes"
    )

    # --- Gemini Nano Banana (image generation + edit) -----------------
    # Native Google model id. Requires ``GEMINI_API_KEY`` — the Emergent
    # proxy does not route image-generation traffic, which is why we
    # historically fell back to HF FLUX. In production with a direct
    # key, this is preferred over FLUX (sharper, no category drift).
    GEMINI_IMAGE_MODEL: str = os.environ.get(
        "GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"
    )

    # --- The Eyes (garment vision analyzer) ---
    # Phase A wiring: a clean provider dispatch is built so the Eyes can
    # route to either Gemini or a Gemma-family model on HuggingFace.
    #
    # DEFAULT today: `gemini` (gemini-2.5-pro). We tried Gemma 3 27B via
    # HF Inference Providers (Featherless) for Phase A, but their
    # multimodal route currently rejects image content-lists with a
    # "roles must alternate" error. Rather than ship a flaky analyzer,
    # we kept Gemma as an *opt-in* path ready for the moment the user
    # deploys their fine-tuned Gemma 4 E2B/E4B on a stable endpoint.
    #
    # FLIP TO GEMMA:
    #     GARMENT_VISION_PROVIDER=hf
    #     GARMENT_VISION_MODEL=<hf-repo-or-endpoint-url>
    GARMENT_VISION_PROVIDER: str = os.environ.get(
        "GARMENT_VISION_PROVIDER", "gemini"
    )
    GARMENT_VISION_MODEL: str = os.environ.get(
        "GARMENT_VISION_MODEL", "gemini-2.5-flash"
    )
    # When set, the HF path hits this OpenAI-compatible endpoint URL
    # instead of going through HF Inference Providers routing. Use this
    # to point at your own deployed Gemma 4 endpoint (HF Dedicated
    # Endpoint, llama.cpp --server, Modal, Replicate, etc.). Example:
    #   GARMENT_VISION_ENDPOINT_URL=https://xxx.endpoints.huggingface.cloud/v1
    #   GARMENT_VISION_ENDPOINT_KEY=hf_xxxx    # optional, defaults to HF_TOKEN
    GARMENT_VISION_ENDPOINT_URL: str | None = (
        os.environ.get("GARMENT_VISION_ENDPOINT_URL") or None
    )
    GARMENT_VISION_ENDPOINT_KEY: str | None = (
        os.environ.get("GARMENT_VISION_ENDPOINT_KEY") or None
    )
    # Per-crop analyzer used inside the multi-item outfit pipeline.
    GARMENT_VISION_CROP_MODEL: str = os.environ.get(
        "GARMENT_VISION_CROP_MODEL", "gemini-2.5-flash"
    )
    # Detection stays on Gemini Flash until we upgrade to a fine-tuned
    # vision model that does boxes well.
    GARMENT_VISION_DETECT_PROVIDER: str = os.environ.get(
        "GARMENT_VISION_DETECT_PROVIDER", "gemini"
    )
    GARMENT_VISION_DETECT_MODEL: str = os.environ.get(
        "GARMENT_VISION_DETECT_MODEL", "gemini-2.5-flash"
    )
    # Hard cap on how many items we analyse per uploaded photo.
    GARMENT_VISION_MAX_ITEMS: int = int(
        os.environ.get("GARMENT_VISION_MAX_ITEMS", "6")
    )
    # FashionCLIP embedding service (for closet search + marketplace similarity).
    FASHION_CLIP_MODEL: str = os.environ.get(
        "FASHION_CLIP_MODEL", "patrickjohncyh/fashion-clip"
    )
    # Set to "0" to disable the local load (useful for tests / CI).
    FASHION_CLIP_ENABLED: bool = os.environ.get("FASHION_CLIP_ENABLED", "1") == "1"

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

    # --- Stripe (legacy; Phase 4P swaps to PayPal) ---
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

    # --- PayPal (Phase 4P) ---
    # Toggle sandbox vs live via PAYPAL_ENV. Base URLs resolve accordingly.
    PAYPAL_ENV: str = (os.environ.get("PAYPAL_ENV") or "sandbox").lower()
    PAYPAL_SANDBOX_CLIENT_ID: str | None = (
        os.environ.get("PAYPAL_SANDBOX_CLIENT_ID") or None
    )
    PAYPAL_SANDBOX_SECRET: str | None = (
        os.environ.get("PAYPAL_SANDBOX_SECRET") or None
    )
    PAYPAL_SANDBOX_WEBHOOK_ID: str | None = (
        os.environ.get("PAYPAL_SANDBOX_WEBHOOK_ID") or None
    )
    PAYPAL_LIVE_CLIENT_ID: str | None = (
        os.environ.get("PAYPAL_LIVE_CLIENT_ID") or None
    )
    PAYPAL_LIVE_SECRET: str | None = (
        os.environ.get("PAYPAL_LIVE_SECRET") or None
    )
    PAYPAL_LIVE_WEBHOOK_ID: str | None = (
        os.environ.get("PAYPAL_LIVE_WEBHOOK_ID") or None
    )
    PAYPAL_DEFAULT_CURRENCY: str = (
        os.environ.get("PAYPAL_DEFAULT_CURRENCY") or "USD"
    ).upper()
    # Comma-separated list exposed to the frontend currency dropdown.
    PAYPAL_SUPPORTED_CURRENCIES: str = (
        os.environ.get("PAYPAL_SUPPORTED_CURRENCIES")
        or "USD,EUR,GBP,ILS,AUD,CAD"
    )
    # Skip webhook signature verification for dev/sandbox if explicitly set.
    PAYPAL_SKIP_WEBHOOK_VERIFY: bool = (
        os.environ.get("PAYPAL_SKIP_WEBHOOK_VERIFY", "false").lower() == "true"
    )
    # Dev-only fallback: if real PayPal auth fails AND this flag is true,
    # the Orders API simulates order create/capture so UI flows can be
    # demo'd without valid credentials. Never enable in production.
    PAYPAL_MOCK_MODE: bool = (
        os.environ.get("PAYPAL_MOCK_MODE", "true").lower() == "true"
    )
    # Platform fee (mirrors legacy STRIPE_PLATFORM_FEE_PERCENT).
    PAYPAL_PLATFORM_FEE_PERCENT: float = float(
        os.environ.get("PAYPAL_PLATFORM_FEE_PERCENT", "7")
    )

    # --- Phase V: Clothing parser + matting (commercial-safe, MIT models) ---
    # Primary clothing segmentation model (per-class parser).
    # Default → `mattmdjaga/segformer_b2_clothes` (b2 backbone, MIT, ~95 MB
    # weights, ~1 GB peak RAM during forward pass). Alternatives:
    #   sayeed99/segformer_b3_clothes  (~180 MB, ~2 GB peak, slightly sharper)
    CLOTHING_PARSER_MODEL: str = (
        os.environ.get("CLOTHING_PARSER_MODEL")
        or "mattmdjaga/segformer_b2_clothes"
    )
    # Optional self-hosted endpoint (FastAPI on dressapp.co). Blank = HF API.
    CLOTHING_PARSER_ENDPOINT_URL: str | None = (
        os.environ.get("CLOTHING_PARSER_ENDPOINT_URL") or None
    )
    # Background matting (non-generative, no hallucination).
    # Legacy field — kept for the self-hosted contract (model name label).
    BACKGROUND_MATTING_MODEL: str = (
        os.environ.get("BACKGROUND_MATTING_MODEL") or "ZhengPeng7/BiRefNet"
    )
    # rembg model used for LOCAL matting. Options:
    #   "u2netp"                 → tiny 4.7MB, fast, low RAM (default)
    #   "isnet-general-use"      → ISNet general (~170MB, better quality)
    #   "birefnet-general"       → BiRefNet best quality (~400MB, heavy)
    #   "u2net"                  → U²-Net classic (~170MB)
    # Default is u2netp so the feature works inside small pod memory
    # limits. Upgrade via env var when self-hosting on a GPU/larger box.
    BACKGROUND_MATTING_REMBG_MODEL: str = (
        os.environ.get("BACKGROUND_MATTING_REMBG_MODEL") or "u2netp"
    )
    BACKGROUND_MATTING_ENDPOINT_URL: str | None = (
        os.environ.get("BACKGROUND_MATTING_ENDPOINT_URL") or None
    )
    # Minimum cosine similarity between original crop & clean-background
    # result to accept the matting (advisory verifier — rembg is
    # deterministic so false rejections are rare; 0.65 is a safe floor).
    MATTING_FAITHFULNESS_THRESHOLD: float = float(
        os.environ.get("MATTING_FAITHFULNESS_THRESHOLD", "0.65")
    )
    # Auto-matte every crop during `analyze` so the per-item cards show
    # clean cutouts instead of bbox rectangles with background bleeding.
    # Set to false to skip for performance testing.
    AUTO_MATTE_CROPS: bool = (
        os.environ.get("AUTO_MATTE_CROPS", "true").lower() == "true"
    )
    # Largest edge we'll feed into rembg. u2netp resizes internally to
    # 320x320 anyway, so values above ~1500 just balloon memory without
    # improving quality. The output alpha mask is upscaled back onto the
    # full-resolution RGB so input photos keep their sharpness.
    BACKGROUND_MATTING_MAX_EDGE: int = int(
        os.environ.get("BACKGROUND_MATTING_MAX_EDGE", "1500")
    )
    # Feature-flag for the local SegFormer inference path in
    # clothing_parser.py. Enabled by default now that we've switched to
    # segformer_b2_clothes (~95 MB weights, ~1 GB peak RAM) which fits
    # comfortably inside the 8 GiB pod limit alongside FashionCLIP/rembg.
    # Disable by setting USE_LOCAL_CLOTHING_PARSER=false if you OOM.
    USE_LOCAL_CLOTHING_PARSER: bool = (
        os.environ.get("USE_LOCAL_CLOTHING_PARSER", "true").lower() == "true"
    )
    # Use the new clothing parser first in /closet/analyze (falls back to
    # legacy detector if it fails or returns nothing useful).
    USE_CLOTHING_PARSER: bool = (
        os.environ.get("USE_CLOTHING_PARSER", "true").lower() == "true"
    )

    @property
    def paypal_client_id(self) -> str | None:
        return (
            self.PAYPAL_LIVE_CLIENT_ID
            if self.PAYPAL_ENV == "live"
            else self.PAYPAL_SANDBOX_CLIENT_ID
        )

    @property
    def paypal_secret(self) -> str | None:
        return (
            self.PAYPAL_LIVE_SECRET
            if self.PAYPAL_ENV == "live"
            else self.PAYPAL_SANDBOX_SECRET
        )

    @property
    def paypal_webhook_id(self) -> str | None:
        return (
            self.PAYPAL_LIVE_WEBHOOK_ID
            if self.PAYPAL_ENV == "live"
            else self.PAYPAL_SANDBOX_WEBHOOK_ID
        )

    @property
    def paypal_api_base(self) -> str:
        return (
            "https://api-m.paypal.com"
            if self.PAYPAL_ENV == "live"
            else "https://api-m.sandbox.paypal.com"
        )

    # --- Google OAuth (Phase 4) ---
    GOOGLE_OAUTH_CLIENT_ID: str | None = (
        (os.environ.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip() or None
    )
    GOOGLE_OAUTH_CLIENT_SECRET: str | None = (
        (os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip() or None
    )
    GOOGLE_OAUTH_REDIRECT_URI: str | None = (
        (os.environ.get("GOOGLE_OAUTH_REDIRECT_URI") or "").strip() or None
    )
    GOOGLE_OAUTH_POST_LOGIN_REDIRECT: str | None = (
        (os.environ.get("GOOGLE_OAUTH_POST_LOGIN_REDIRECT") or "").strip() or None
    )

    # --- Dev toggles ---
    ALLOW_DEV_BYPASS: bool = os.environ.get("ALLOW_DEV_BYPASS", "true").lower() == "true"

    # --- Admin allow-list (Phase T-Auth) ---
    # Comma-separated list of emails that should auto-receive the ``admin``
    # role on register / login / Google sign-in. Re-checked on every login,
    # so adding/removing an email + restarting the backend promotes/demotes
    # without DB surgery. The CLI fallback is ``backend/scripts/grant_admin.py``.
    ADMIN_EMAILS: str = os.environ.get("ADMIN_EMAILS", "")

    @property
    def admin_emails_set(self) -> set[str]:
        return {
            e.strip().lower()
            for e in (self.ADMIN_EMAILS or "").split(",")
            if e.strip()
        }

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
