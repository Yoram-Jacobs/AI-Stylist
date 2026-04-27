"""Template showing every environment variable DressApp expects.

Copy this file's KEY LIST into `/app/backend/.env` (no code is read from this
template at runtime). This file is committed; the real `.env` is not.
"""

REQUIRED_FOR_POC = [
    # LLM — at least ONE of these must be set:
    #   * EMERGENT_LLM_KEY   → dev preview, routes through Emergent proxy
    #   * GEMINI_API_KEY     → production, talks to Google directly + enables
    #                          Nano Banana image generation
    "EMERGENT_LLM_KEY",
    "GEMINI_API_KEY",
    # Vision (Hugging Face SegFormer for cutout/segmentation)
    "HF_TOKEN",
    # Voice input (Groq Whisper-v3)
    "GROQ_API_KEY",
    # Voice output (Deepgram Aura-2 with WebSocket streaming)
    "DEEPGRAM_API_KEY",
    # Weather context
    "OPENWEATHER_API_KEY",
]

REQUIRED_FOR_PHASE_4 = [
    # Stripe Connect Express marketplace
    "STRIPE_SECRET_KEY",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_WEBHOOK_SECRET",
    # Google Calendar OAuth
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_REDIRECT_URI",
]

OPTIONAL = [
    "JWT_SECRET",
    "JWT_ALGORITHM",
    "JWT_EXPIRES_MIN",
    "CORS_ORIGINS",
    "ALLOW_DEV_BYPASS",
]
