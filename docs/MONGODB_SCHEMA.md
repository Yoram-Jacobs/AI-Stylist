# DressApp — MongoDB Schema (Phase 1)

> All documents use `id: UUID (string)` as the public identifier. The native `_id` is excluded from API responses.  
> Timestamps are ISO-8601 strings (not `BSON Date`) to avoid the classic `datetime not JSON serializable` pitfall.  
> All monetary amounts are stored as **cents/minor units** (integers) to avoid float drift.

---

## Collections & Indexes

| Collection         | Purpose                                              | Key Indexes                                                                         |
|--------------------|------------------------------------------------------|-------------------------------------------------------------------------------------|
| `users`            | Auth + profile + style preferences + OAuth tokens    | `email` (unique), `stripe_account_id`                                                |
| `closet_items`     | User's wardrobe items                                | `user_id`, `source`, `category`, text index on `tags`                                |
| `listings`         | Marketplace items (subset of closet_items or retail) | `source`, `status`, `seller_id`, `category`, 2dsphere on `location`                   |
| `transactions`     | Money ledger for marketplace sales                   | `buyer_id`, `seller_id`, `listing_id`, `status`, `stripe_checkout_session_id`        |
| `stylist_sessions` | Per-user agent memory (Durable Object equivalent)    | `user_id` (unique)                                                                    |
| `stylist_messages` | Conversation turns within a session                  | `(session_id, created_at)` compound                                                    |
| `embeddings`       | Vector store for items / outfits / text queries      | `entity_type`, `entity_id`; **Atlas Vector Search** on `vector`                       |
| `cultural_rules`   | Regional / religious / occasion constraints          | `(region, religion, occasion)` compound                                                |
| `trend_reports`    | Daily Trend-Scout summaries                          | `date`, `category`                                                                    |
| `outfits`          | Saved AI-generated outfits for later reuse           | `user_id`, `created_at`                                                                |

---

## 1. `users`

```json
{
  "id": "uuid",
  "email": "user@example.com",
  "password_hash": "bcrypt$...",           // null if OAuth-only
  "display_name": "Alex",
  "avatar_url": "https://...",
  "locale": "en-US",
  "preferred_language": "en",              // Whisper / Deepgram / Gemini language
  "preferred_voice_id": "aura-2-thalia-en",// Deepgram Aura-2 voice
  "home_location": { "lat": 40.7128, "lng": -74.0060, "city": "New York" },
  "style_profile": {
    "aesthetics": ["minimalist", "smart-casual"],
    "color_palette": ["navy", "ivory", "olive"],
    "avoid": ["neon", "logos"],
    "body_notes": "tall, athletic",
    "budget_monthly_cents": 15000
  },
  "cultural_context": {
    "region": "US",
    "religion": null,
    "dress_conservativeness": "moderate"
  },
  "google_oauth": {                         // stored only after /oauth/google/callback
    "access_token": "...",
    "refresh_token": "...",
    "expires_at": "2025-01-01T00:00:00Z",
    "scopes": ["https://www.googleapis.com/auth/calendar.readonly"]
  },
  "stripe_account_id": "acct_xxx",          // Stripe Connect Express (seller side)
  "stripe_onboarding_complete": false,
  "roles": ["user"],                        // 'admin' for backoffice
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z"
}
```

---

## 2. `closet_items`

```json
{
  "id": "uuid",
  "user_id": "uuid",
  "source": "Private",                      // SOURCE TAG: 'Private' | 'Shared' | 'Retail'
  "category": "top",                        // top | bottom | outerwear | shoes | accessory | dress | full_outfit
  "sub_category": "shirt",
  "title": "White Oxford Shirt",
  "brand": "Uniqlo",
  "size": "M",
  "color": "white",
  "material": "cotton",
  "pattern": "solid",
  "season": ["spring", "summer", "fall"],
  "formality": "smart-casual",              // casual | smart-casual | business | formal
  "cultural_tags": [],                       // e.g. ['modest', 'hijab-friendly']
  "tags": ["oxford", "office", "layerable"],
  "original_image_url": "s3://.../raw.jpg",
  "segmented_image_url": "s3://.../segmented.png",
  "embedding_id": "uuid",                    // FK → embeddings.id
  "purchase_price_cents": 3500,
  "purchase_currency": "USD",
  "purchase_date": "2024-03-01",
  "wear_count": 14,
  "last_worn_at": "2024-12-20T08:00:00Z",
  "notes": "Slightly small in shoulders",
  "retail_metadata": null,                   // populated when source='Retail'
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z"
}
```

`retail_metadata` (only when `source = 'Retail'`):

```json
{
  "retailer_name": "Zara",
  "product_url": "https://...",
  "sku": "...",
  "list_price_cents": 4500,
  "currency": "USD",
  "availability": "in_stock"
}
```

---

## 3. `listings`

Listings are marketplace-facing projections of a `closet_item`. Private items are listable as Shared/Retail only.

```json
{
  "id": "uuid",
  "closet_item_id": "uuid",                  // nullable if pure retail dropship
  "seller_id": "uuid",                       // users.id
  "source": "Shared",                        // 'Shared' | 'Retail'  (never 'Private')
  "mode": "sell",                             // sell | swap | donate
  "title": "White Oxford Shirt — worn twice",
  "description": "Barely worn, from smoke-free home.",
  "category": "top",
  "size": "M",
  "condition": "like_new",                   // new | like_new | good | fair
  "images": ["s3://..."],
  "location": { "type": "Point", "coordinates": [-74.006, 40.7128] },
  "ships_to": ["US", "CA"],
  "financial_metadata": {                    // FINANCIAL METADATA — required
    "list_price_cents": 2500,
    "currency": "USD",
    "platform_fee_percent": 7,
    "platform_fee_applied_after": "stripe_processing_fee",
    "stripe_processing_fee_percent": 2.9,
    "stripe_processing_fee_fixed_cents": 30,
    "estimated_seller_net_cents": 2224       // pre-computed preview for UI
  },
  "status": "active",                        // draft | active | reserved | sold | removed
  "views": 0,
  "favorites": 0,
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z"
}
```

---

## 4. `transactions`

One document per marketplace payment. Gross, Stripe fees, platform fees and seller net are stored explicitly so the admin dashboard never has to recompute.

```json
{
  "id": "uuid",
  "listing_id": "uuid",
  "buyer_id": "uuid",
  "seller_id": "uuid",
  "currency": "USD",
  "financial": {                              // FINANCIAL METADATA (immutable ledger)
    "gross_cents": 2500,
    "stripe_fee_cents": 103,                  // round(2500*0.029 + 30) = 103
    "net_after_stripe_cents": 2397,
    "platform_fee_percent": 7,
    "platform_fee_cents": 168,                // round(2397 * 0.07) = 168
    "seller_net_cents": 2229,
    "platform_fee_applied_after": "stripe_processing_fee"
  },
  "stripe": {
    "checkout_session_id": "cs_...",
    "payment_intent_id": "pi_...",
    "transfer_id": "tr_...",
    "destination_account": "acct_xxx"         // seller's Stripe Connect account
  },
  "status": "paid",                           // pending | paid | refunded | failed | disputed
  "paid_at": "2025-01-01T00:00:00Z",
  "refunded_at": null,
  "created_at": "2025-01-01T00:00:00Z"
}
```

---

## 5. `stylist_sessions` (Durable Object equivalent)

One per user — holds persistent agent memory.

```json
{
  "id": "uuid",
  "user_id": "uuid",                         // unique index
  "active_conversation_id": "uuid",
  "memory": {
    "long_term_preferences": ["prefers layering", "dislikes pastels"],
    "recent_outfits": [
      { "outfit_id": "uuid", "rating": 5, "occasion": "date night" }
    ],
    "feedback_signals": {
      "liked_tags": { "minimalist": 12, "linen": 7 },
      "disliked_tags": { "neon": 3 }
    }
  },
  "turns": 42,
  "last_active_at": "2025-01-01T00:00:00Z",
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z"
}
```

### `stylist_messages`

```json
{
  "id": "uuid",
  "session_id": "uuid",
  "role": "user",                             // user | assistant | tool
  "input_modality": "image+voice",            // text | voice | image | image+text | image+voice
  "transcript": "What should I wear to the client meeting tomorrow?",
  "image_refs": ["s3://.../img.jpg"],
  "context": {
    "weather": { "temp_c": 6, "condition": "rain" },
    "calendar": [{ "title": "Client pitch", "start": "...", "formality_hint": "business" }]
  },
  "assistant_payload": {
    "outfit_recommendations": [
      {
        "name": "Navy suit + light blue oxford",
        "items": [
          { "closet_item_id": "uuid", "role": "top" },
          { "closet_item_id": "uuid", "role": "bottom" }
        ],
        "why": "Weather calls for layers; calendar has a client pitch at 10am."
      }
    ],
    "reasoning_summary": "...",
    "shopping_suggestions": [],
    "do_dont": []
  },
  "tts_audio_ref": "s3://.../reply.mp3",
  "latency_ms": { "whisper": 420, "sam": 650, "gemini": 1800, "deepgram": 210 },
  "created_at": "2025-01-01T00:00:00Z"
}
```

---

## 6. `embeddings` (Vectorize equivalent)

```json
{
  "id": "uuid",
  "entity_type": "closet_item",               // closet_item | listing | outfit | query
  "entity_id": "uuid",
  "model": "clip-vit-l-14",                   // or sentence-transformers/all-MiniLM-L6-v2 for text
  "vector": [0.012, -0.034, ...],             // 512 or 768 dims
  "metadata": {
    "category": "top",
    "color": "white",
    "user_id": "uuid"
  },
  "created_at": "2025-01-01T00:00:00Z"
}
```

**Atlas Vector Search index** (to be created in Phase 2):

```json
{
  "mappings": {
    "dynamic": false,
    "fields": {
      "vector": { "type": "knnVector", "dimensions": 512, "similarity": "cosine" },
      "entity_type": { "type": "token" },
      "metadata.user_id": { "type": "token" }
    }
  }
}
```

Fallback (if Atlas Vector Search not available on the Emergent-managed Mongo): cosine similarity computed in-process with a small FAISS index hydrated on startup.

---

## 7. `cultural_rules`

```json
{
  "id": "uuid",
  "region": "SA",
  "religion": "islam",
  "occasion": "mosque",
  "rules": {
    "required": ["cover_shoulders", "cover_knees", "no_sheer_fabric"],
    "recommended": ["loose_fit", "neutral_colors"],
    "disallowed": ["shorts", "sleeveless"]
  },
  "source": "editor",
  "priority": 10,
  "created_at": "2025-01-01T00:00:00Z"
}
```

The stylist prompt merges the user's `cultural_context` with matching `cultural_rules` as hard constraints.

---

## 8. `trend_reports`

```json
{
  "id": "uuid",
  "date": "2025-01-01",
  "category": "womens_ss25",
  "headline": "Butter yellow dominates Milan",
  "summary_md": "...",
  "sources": ["https://vogue.com/...", "https://bof.com/..."],
  "key_items": [
    { "name": "butter-yellow tailored blazer", "expected_price_band": "mid" }
  ],
  "generated_by": "trend-scout-agent@1.0",
  "created_at": "2025-01-01T06:00:00Z"
}
```

---

## 9. `outfits`

```json
{
  "id": "uuid",
  "user_id": "uuid",
  "title": "Rainy Tuesday client meeting",
  "items": [
    { "closet_item_id": "uuid", "role": "top" },
    { "closet_item_id": "uuid", "role": "bottom" },
    { "closet_item_id": "uuid", "role": "outerwear" }
  ],
  "source": "stylist_agent",
  "context_at_creation": {
    "weather": { "temp_c": 6, "condition": "rain" },
    "calendar": [{ "title": "Client pitch", "formality_hint": "business" }]
  },
  "user_rating": 5,
  "worn_on": ["2025-01-08"],
  "created_at": "2025-01-01T00:00:00Z"
}
```

---

## 10. Index creation (idempotent bootstrap on FastAPI startup)

```python
await db.users.create_index("email", unique=True)
await db.users.create_index("stripe_account_id")
await db.closet_items.create_index([("user_id", 1), ("source", 1), ("category", 1)])
await db.closet_items.create_index([("tags", "text"), ("title", "text"), ("brand", "text")])
await db.listings.create_index([("source", 1), ("status", 1), ("category", 1)])
await db.listings.create_index([("location", "2dsphere")])
await db.transactions.create_index([("buyer_id", 1), ("created_at", -1)])
await db.transactions.create_index([("seller_id", 1), ("created_at", -1)])
await db.transactions.create_index("stripe.checkout_session_id", unique=True, sparse=True)
await db.stylist_sessions.create_index("user_id", unique=True)
await db.stylist_messages.create_index([("session_id", 1), ("created_at", -1)])
await db.embeddings.create_index([("entity_type", 1), ("entity_id", 1)], unique=True)
await db.cultural_rules.create_index([("region", 1), ("religion", 1), ("occasion", 1)])
await db.trend_reports.create_index([("date", -1), ("category", 1)])
```
