"""Pydantic v2 models that mirror the MongoDB schema.

All datetimes are serialised as ISO-8601 strings to avoid the
"datetime is not JSON serializable" MongoDB pitfall.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


Source = Literal["Private", "Shared", "Retail"]
ListingSource = Literal["Shared", "Retail"]
ListingMode = Literal["sell", "swap", "donate"]
ListingStatus = Literal["draft", "active", "reserved", "sold", "removed"]
TxStatus = Literal["pending", "paid", "refunded", "failed", "disputed"]
Formality = Literal["casual", "smart-casual", "business", "formal"]
Condition = Literal["new", "like_new", "good", "fair"]
# Rich closet-item enums (used by AddItem flow + The Eyes analyzer)
GarmentState = Literal["new", "used"]
GarmentCondition = Literal["bad", "fair", "good", "excellent"]
GarmentQuality = Literal["budget", "mid", "premium", "luxury"]
GarmentGender = Literal["men", "women", "unisex", "kids"]
MarketplaceIntent = Literal["own", "for_sale", "donate", "swap"]
DressCode = Literal[
    "casual", "smart-casual", "business", "formal", "athletic", "loungewear"
]


class WeightedTag(BaseModel):
    """Generic ``{name, pct}`` pair used for colours and fabric composition."""
    name: str
    pct: int | None = None  # 0..100, optional (e.g. "red" without %)


class BaseDoc(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    id: str = Field(default_factory=_new_id)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


# --------------------------- Users ---------------------------
class StyleProfile(BaseModel):
    aesthetics: list[str] = Field(default_factory=list)
    color_palette: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    body_notes: str | None = None
    budget_monthly_cents: int | None = None


class CulturalContext(BaseModel):
    region: str | None = None
    religion: str | None = None
    dress_conservativeness: Literal["low", "moderate", "high"] | None = None


class GoogleOAuthTokens(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: str
    scopes: list[str] = Field(default_factory=list)


class User(BaseDoc):
    email: EmailStr
    password_hash: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    locale: str = "en-US"
    preferred_language: str = "en"
    preferred_voice_id: str = "aura-2-thalia-en"
    home_location: dict[str, Any] | None = None
    style_profile: StyleProfile = Field(default_factory=StyleProfile)
    cultural_context: CulturalContext = Field(default_factory=CulturalContext)
    google_oauth: GoogleOAuthTokens | None = None
    stripe_account_id: str | None = None
    stripe_onboarding_complete: bool = False
    roles: list[str] = Field(default_factory=lambda: ["user"])


# ------------------------- Closet items -------------------------
class RetailMetadata(BaseModel):
    retailer_name: str
    product_url: str
    sku: str | None = None
    list_price_cents: int
    currency: str = "USD"
    availability: Literal["in_stock", "low", "out_of_stock"] = "in_stock"


class ClosetItem(BaseDoc):
    user_id: str
    source: Source = "Private"
    # Descriptive
    name: str | None = None  # short, friendly — may differ from title
    title: str
    caption: str | None = None
    # Taxonomy (rich, used by The Eyes)
    category: str
    sub_category: str | None = None
    item_type: str | None = None
    brand: str | None = None
    gender: GarmentGender | None = None
    dress_code: DressCode | None = None
    season: list[str] = Field(default_factory=list)
    tradition: str | None = None  # e.g. "arabic", "jewish"; free-form
    # Structured composition
    size: str | None = None
    color: str | None = None  # keep for backward compat (dominant colour)
    colors: list[WeightedTag] = Field(default_factory=list)
    material: str | None = None
    fabric_materials: list[WeightedTag] = Field(default_factory=list)
    pattern: str | None = None
    # Quality & state
    state: GarmentState | None = None
    condition: GarmentCondition | None = None
    quality: GarmentQuality | None = None
    repair_advice: str | None = None  # populated by The Eyes when condition == bad
    # Pricing & marketplace intent
    price_cents: int | None = None
    currency: str = "USD"
    marketplace_intent: MarketplaceIntent = "own"
    listing_id: str | None = None  # set when auto-listed on save
    # Legacy / compatibility
    formality: Formality | None = None
    cultural_tags: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # Media + persistence
    original_image_url: str | None = None
    segmented_image_url: str | None = None
    segmentation_model: str | None = None
    # Phase Q — Wardrobe Reconstructor
    reconstructed_image_url: str | None = None
    reconstruction_metadata: dict[str, Any] | None = None
    variants: list[dict[str, Any]] = Field(default_factory=list)
    embedding_id: str | None = None
    # Purchase history
    purchase_price_cents: int | None = None
    purchase_currency: str = "USD"
    purchase_date: str | None = None
    wear_count: int = 0
    last_worn_at: str | None = None
    notes: str | None = None
    retail_metadata: RetailMetadata | None = None


# ----------------- The Eyes: analyzer response payload -----------------
class GarmentAnalysis(BaseModel):
    """Structured output returned by ``POST /api/v1/closet/analyze``.

    Every field is optional so the caller can show an editable form even
    if the model is uncertain. ``model_used`` surfaces which AI provider
    produced the analysis for telemetry.
    """
    name: str | None = None
    title: str | None = None
    caption: str | None = None
    category: str | None = None
    sub_category: str | None = None
    item_type: str | None = None
    brand: str | None = None
    gender: str | None = None
    dress_code: str | None = None
    season: list[str] = Field(default_factory=list)
    tradition: str | None = None
    colors: list[WeightedTag] = Field(default_factory=list)
    fabric_materials: list[WeightedTag] = Field(default_factory=list)
    pattern: str | None = None
    state: str | None = None
    condition: str | None = None
    quality: str | None = None
    size: str | None = None
    price_cents: int | None = None
    repair_advice: str | None = None
    tags: list[str] = Field(default_factory=list)
    model_used: str | None = None
    raw: dict[str, Any] | None = None


# -------------------------- Listings --------------------------
class FinancialMetadata(BaseModel):
    list_price_cents: int
    currency: str = "USD"
    platform_fee_percent: float = 7.0
    platform_fee_applied_after: Literal["stripe_processing_fee", "gross"] = (
        "stripe_processing_fee"
    )
    stripe_processing_fee_percent: float = 2.9
    stripe_processing_fee_fixed_cents: int = 30
    estimated_seller_net_cents: int


class Listing(BaseDoc):
    closet_item_id: str | None = None
    seller_id: str
    source: ListingSource
    mode: ListingMode = "sell"
    title: str
    description: str | None = None
    category: str
    size: str | None = None
    condition: Condition = "good"
    images: list[str] = Field(default_factory=list)
    location: dict[str, Any] | None = None
    ships_to: list[str] = Field(default_factory=list)
    financial_metadata: FinancialMetadata
    status: ListingStatus = "active"
    views: int = 0
    favorites: int = 0


# ------------------------- Transactions -------------------------
class TransactionFinancial(BaseModel):
    gross_cents: int
    stripe_fee_cents: int
    net_after_stripe_cents: int
    platform_fee_percent: float = 7.0
    platform_fee_cents: int
    seller_net_cents: int
    platform_fee_applied_after: Literal["stripe_processing_fee", "gross"] = (
        "stripe_processing_fee"
    )


class StripePointer(BaseModel):
    checkout_session_id: str | None = None
    payment_intent_id: str | None = None
    transfer_id: str | None = None
    destination_account: str | None = None


class Transaction(BaseDoc):
    listing_id: str
    buyer_id: str
    seller_id: str
    currency: str = "USD"
    financial: TransactionFinancial
    stripe: StripePointer = Field(default_factory=StripePointer)
    status: TxStatus = "pending"
    paid_at: str | None = None
    refunded_at: str | None = None


# --------------------- Stylist session memory ---------------------
class StylistSession(BaseDoc):
    user_id: str
    active_conversation_id: str | None = None
    memory: dict[str, Any] = Field(default_factory=dict)
    turns: int = 0
    last_active_at: str = Field(default_factory=_now_iso)


class StylistMessage(BaseDoc):
    session_id: str
    role: Literal["user", "assistant", "tool"]
    input_modality: Literal[
        "text", "voice", "image", "image+text", "image+voice", "tool_result"
    ]
    transcript: str | None = None
    image_refs: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    assistant_payload: dict[str, Any] | None = None
    tts_audio_ref: str | None = None
    latency_ms: dict[str, int] = Field(default_factory=dict)


# ---------------- Stylist response (public API contract) ----------------
class OutfitItem(BaseModel):
    closet_item_id: str | None = None
    role: str  # 'top', 'bottom', 'outerwear', 'shoes', 'accessory'
    description: str | None = None


class OutfitRecommendation(BaseModel):
    name: str
    items: list[OutfitItem] = Field(default_factory=list)
    why: str
    confidence: float = 0.8


class StylistAdvice(BaseModel):
    transcript: str | None = None
    segmented_image_url: str | None = None
    infilled_image_url: str | None = None
    weather_summary: str | None = None
    calendar_summary: str | None = None
    outfit_recommendations: list[OutfitRecommendation] = Field(default_factory=list)
    reasoning_summary: str
    shopping_suggestions: list[str] = Field(default_factory=list)
    do_dont: list[str] = Field(default_factory=list)
    tts_audio_base64: str | None = None
    latency_ms: dict[str, int] = Field(default_factory=dict)
