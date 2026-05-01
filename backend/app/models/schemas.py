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

    # --- Extended profile (Phase T) -------------------------------------
    # Plain identity — populated from OAuth `given_name` / `family_name` on
    # first Google connect, editable afterwards.
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    date_of_birth: str | None = None  # ISO YYYY-MM-DD
    sex: Literal["male", "female"] | None = None
    personal_status: Literal[
        "single", "married", "divorced", "widowed"
    ] | None = None
    address: dict[str, Any] | None = None  # {line1,line2,city,region,country,postal_code}

    # Unit preferences: weight (kg | lb) + length (cm | in).
    units: dict[str, Any] | None = None

    # Photos — stored as data URLs so we stay inside the current serverless
    # Mongo footprint (no external blob store yet). Capped client-side to
    # ~500 KB each.
    face_photo_url: str | None = None
    body_photo_url: str | None = None

    # Body measurements kept in one nested doc so adding a field later is a
    # one-line change and doesn't bloat the user root document.
    body_measurements: dict[str, Any] | None = None

    # Hair profile (length / type / color / style).
    hair: dict[str, Any] | None = None

    # --- Phase 4P: PayPal payouts ---
    # Email address used to receive seller payouts via PayPal Payouts API.
    paypal_receiver_email: str | None = None

    # --- Professional (Phase U) ----------------------------------------
    # Self-service "is fashion professional?" toggle + business card.
    # When is_professional=True the user appears in the /experts directory
    # (unless approval_status='hidden' by admin moderation).
    professional: dict[str, Any] | None = None


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
    # Phase V6 — EU Digital Product Passport (DPP) data imported via
    # QR scan. Stored verbatim as a nested document so the UI can render
    # full provenance (materials %, carbon footprint, country of origin,
    # care & repair instructions, certifications, source URL, ...)
    # without polluting the flat taxonomy fields.
    dpp_data: dict[str, Any] | None = None
    # ---- Phase Z2 — duplicate-photo detection ----
    # The Eyes' deterministic pre-flight check uses these three fields
    # (computed in-browser before upload, no LLM cost) to spot the case
    # "user uploaded the same JPEG twice". Only the SHA-256 is used for
    # equality; ``source_filename`` and ``source_size_bytes`` are kept
    # for diagnostics / UI ("we matched IMG_1742.jpg / 4.2 MB"). All
    # three are nullable so legacy items remain valid.
    source_sha256: str | None = None
    source_filename: str | None = None
    source_size_bytes: int | None = None
    # Phase Z2.1 — 64-bit average-hash of the photo (16-char hex).
    # Used by /closet/preflight to catch visual duplicates of legacy
    # items whose ``source_sha256`` was never captured (the original
    # bytes weren't stored). Backfilled lazily from
    # ``thumbnail_data_url`` / ``segmented_image_url`` / etc. on the
    # first /preflight call that touches the row.
    source_phash: str | None = None
    # Set to ``True`` when the user explicitly approved adding a photo
    # the pre-flight flagged as a duplicate. The closet UI overlays a
    # red ⭐ on these cards, and the Stylist Brain filters them out of
    # the recommendation pool to prevent doubled-up outfit suggestions.
    is_duplicate: bool = False


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
    # ``auto_created=True`` marks listings created automatically when
    # a closet item is shared. The frontend uses this flag to display
    # a "Complete listing" CTA on the closet card, prompting the
    # user to refine price / mode / description before serious
    # browsing happens.
    auto_created: bool = False


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


class PayPalPointer(BaseModel):
    """Persisted on a Transaction once the PayPal flow is initiated."""

    order_id: str | None = None
    capture_id: str | None = None
    payer_id: str | None = None
    payer_email: str | None = None
    status: str | None = None  # COMPLETED, PENDING, DENIED, REFUNDED
    payout_batch_id: str | None = None
    payout_item_id: str | None = None
    payout_status: str | None = None  # SUCCESS, PENDING, FAILED, BLOCKED
    captured_at: str | None = None


class Transaction(BaseDoc):
    listing_id: str
    buyer_id: str
    seller_id: str
    currency: str = "USD"
    financial: TransactionFinancial
    stripe: StripePointer = Field(default_factory=StripePointer)
    paypal: PayPalPointer = Field(default_factory=PayPalPointer)
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
    title: str | None = None
    snippet: str | None = None
    archived: bool = False


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
    # --- Phase S: horizon expansion ----------------------------------
    # Populated by ``stylist_widen.widen_stylist_response`` when the
    # primary advice references items the user doesn't own (or the user
    # explicitly toggled "Search wider"). All optional / empty by default
    # so old chat clients keep rendering normally.
    marketplace_suggestions: list["MarketplaceSuggestion"] = Field(default_factory=list)
    fashion_scout_picks: list[dict[str, Any]] = Field(default_factory=list)
    generated_examples: list[dict[str, Any]] = Field(default_factory=list)
    widened_for: list[str] = Field(default_factory=list)
    applied_preferences: list[str] = Field(default_factory=list)


# --------------------- Phase R: Outfit Composer (Stylist Power-Up) ---------------------
# Schema design notes:
# - These are returned alongside the existing StylistAdvice contract so old
#   chat clients keep working; the canvas is opt-in via a tap-to-expand UI.
# - Persisted inside ``StylistMessage.assistant_payload`` under the key
#   ``outfit_canvas`` so the canvas survives chat history + sharing.
# - Marketplace + pro suggestions are *included* in the canvas envelope
#   rather than separate API calls so the UI renders atomically — fewer
#   round-trips, no flicker.

OutfitSlotRole = Literal[
    "top", "bottom", "dress", "outerwear", "shoes", "accessory", "bag", "headwear"
]


class CandidateGarment(BaseModel):
    """One uploaded image after garment_vision analysis + dedup grouping."""

    candidate_id: str  # uuid for client cross-references
    source: Literal["upload", "closet"] = "upload"
    image_data_url: str | None = None  # small data URL preview (<= 60 KB)
    closet_item_id: str | None = None  # set when source='closet'
    title: str | None = None
    category: str | None = None
    sub_category: str | None = None
    color: str | None = None
    pattern: str | None = None
    material: str | None = None
    brand: str | None = None
    formality: str | None = None
    season: str | None = None
    tags: list[str] = Field(default_factory=list)
    quality_score: float = 0.0  # internal — composer's confidence the analysis is good
    brief_match_score: float = 0.0  # 0..1 — how well candidate fits the user's brief
    dedup_group_id: str | None = None  # candidates sharing this id are near-duplicates


class OutfitSlot(BaseModel):
    role: OutfitSlotRole
    candidate_id: str | None = None  # references CandidateGarment.candidate_id
    rationale: str | None = None
    is_gap: bool = False  # True when no candidate fills this slot — drives marketplace strip


class RejectedCandidate(BaseModel):
    candidate_id: str
    reason: Literal[
        "duplicate", "wrong_category", "color_clash",
        "wrong_formality", "wrong_season", "off_brief", "low_quality"
    ]
    detail: str | None = None
    kept_candidate_id: str | None = None  # for 'duplicate' — points at the surviving twin


class MarketplaceSuggestion(BaseModel):
    listing_id: str
    title: str
    image_url: str | None = None
    price_cents: int | None = None
    currency: str | None = None
    seller_display_name: str | None = None
    fills_slot: OutfitSlotRole | None = None
    match_score: float = 0.0
    why: str | None = None


class ProfessionalSuggestion(BaseModel):
    professional_id: str
    display_name: str
    profession: str | None = None
    avatar_url: str | None = None
    location: str | None = None
    why_suggested: str  # human-readable rationale, e.g. "Alterations needed for the wedding suit"
    triggered_by: list[str] = Field(default_factory=list)  # which keywords/signals fired


class OutfitCanvas(BaseModel):
    """Top-level structured response for the Stylist Composer."""

    canvas_id: str
    schema_version: int = 1
    brief: str
    language: str = "en"
    summary: str  # short text summary shown as a chat bubble
    detailed_rationale: str | None = None
    slots: list[OutfitSlot] = Field(default_factory=list)
    candidates: list[CandidateGarment] = Field(default_factory=list)
    rejected: list[RejectedCandidate] = Field(default_factory=list)
    marketplace_suggestions: list[MarketplaceSuggestion] = Field(default_factory=list)
    professional_suggestion: ProfessionalSuggestion | None = None
    model_used: str | None = None
    latency_ms: dict[str, int] = Field(default_factory=dict)


# --------------------- Phase U: Ad Campaigns ---------------------
AdCampaignStatus = Literal["draft", "active", "paused", "ended", "disabled"]


class AdCreative(BaseModel):
    headline: str
    body: str | None = None
    image_url: str | None = None
    cta_label: str | None = None
    cta_url: str | None = None


class AdCampaign(BaseDoc):
    owner_id: str
    name: str
    profession: str | None = None  # Stylist, Barber, Fashion designer, etc.
    creative: AdCreative
    # Billing (counters only for MVP — PayPlus not yet wired).
    daily_budget_cents: int = 0
    bid_cents: int = 0  # auction-lite weight
    # Scheduling window (ISO dates).
    start_date: str | None = None
    end_date: str | None = None
    # Regional targeting.
    target_country: str | None = None  # ISO-2 (e.g. IL, US)
    target_region: str | None = None  # region/state name (free-form for MVP)
    status: AdCampaignStatus = "draft"
    # When the serving layer auto-pauses a campaign (e.g. insufficient
    # funds) we surface the reason so the UI can render a helpful banner.
    status_reason: str | None = None
    # Per-currency billing: campaigns draw from the owner's matching
    # `user_credits(user_id, currency)` balance. Default USD for MVP.
    currency: str = "USD"
    # Live counters.
    impressions: int = 0
    clicks: int = 0
    spent_cents: int = 0


# --------------------- Phase 4P: Credits + Payments ---------------------
CreditTopupStatus = Literal["pending", "captured", "failed", "refunded"]


class UserCredits(BaseDoc):
    """Per-(user, currency) prepaid ad credit balance."""

    user_id: str
    currency: str = "USD"
    balance_cents: int = 0


class CreditTopup(BaseDoc):
    user_id: str
    amount_cents: int
    currency: str = "USD"
    status: CreditTopupStatus = "pending"
    paypal_order_id: str | None = None
    paypal_capture_id: str | None = None
    captured_at: str | None = None
    payer_email: str | None = None
    pack: str | None = None  # "10" | "25" | "50" | "custom"
