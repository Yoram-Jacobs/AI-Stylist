"""
Seed the database with demo data so a fresh deployment doesn't look empty.

Usage (inside the deployed backend container):
    python -m scripts.seed_demo

Reads ``MONGO_URL`` and ``DB_NAME`` from env (already provided by the
container). Idempotent: re-running is safe — it upserts by stable IDs.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta

from motor.motor_asyncio import AsyncIOMotorClient


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_in_days(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


# Stable IDs so re-runs upsert instead of duplicating.
DEMO_USER_IDS = ["demo-user-0001", "demo-user-0002", "demo-user-0003", "demo-user-0004", "demo-user-0005"]
DEMO_PRO_IDS = ["demo-pro-stylist", "demo-pro-tailor", "demo-pro-designer"]
DEMO_LISTING_IDS = [f"demo-listing-{i:02d}" for i in range(1, 9)]
DEMO_CAMPAIGN_IDS = [f"demo-campaign-{i:02d}" for i in range(1, 4)]
DEMO_CLOSET_IDS = [f"demo-closet-{i:02d}" for i in range(1, 6)]


async def seed_user(db) -> None:
    """Five demo customers + three professional profiles."""
    demo_users = [
        {
            "id": DEMO_USER_IDS[0],
            "email": "demo1@dressapp.co",
            "display_name": "Demo User 1",
            "first_name": "Demo1",
            "last_name": "User",
            "locale": "en-US",
            "preferred_language": "en",
            "preferred_voice_id": "aura-2-thalia-en",
            "style_profile": {
                "aesthetics": ["minimalist", "smart-casual"],
                "color_palette": ["navy", "cream", "olive"],
                "avoid": ["neon"],
                "body_notes": None,
                "budget_monthly_cents": 25000,
            },
            "cultural_context": {
                "region": "US",
                "religion": None,
                "dress_conservativeness": "moderate",
            },
            "roles": ["user"],
            "is_demo": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
        {
            "id": DEMO_USER_IDS[1],
            "email": "demo2@dressapp.co",
            "display_name": "Demo User 2",
            "first_name": "Demo2",
            "last_name": "User",
            "locale": "en-US",
            "preferred_language": "en",
            "preferred_voice_id": "aura-2-thalia-en",
            "style_profile": {
                "aesthetics": ["minimalist", "smart-casual"],
                "color_palette": ["black", "white", "red"],
                "avoid": ["colorful"],
                "body_notes": None,
                "budget_monthly_cents": 25000,
            },
            "cultural_context": {
                "region": "GR",
                "religion": None,
                "dress_conservativeness": "moderate",
            },
            "roles": ["user"],
            "is_demo": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
        {
            "id": DEMO_USER_IDS[2],
            "email": "demo3@dressapp.co",
            "display_name": "Demo User 3",
            "first_name": "Demo3",
            "last_name": "User",
            "locale": "he-IL",
            "preferred_language": "he",
            "preferred_voice_id": "aura-2-thalia-en",
            "style_profile": {
                "aesthetics": ["minimalist", "smart-casual"],
                "color_palette": ["black", "white", "red"],
                "avoid": ["colorful"],
                "body_notes": None,
                "budget_monthly_cents": 25000,
            },
            "cultural_context": {
                "region": "IL",
                "religion": None,
                "dress_conservativeness": "moderate",
            },
            "roles": ["user"],
            "is_demo": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
        {
            "id": DEMO_USER_IDS[3],
            "email": "demo4@dressapp.co",
            "display_name": "Demo User 4",
            "first_name": "Demo4",
            "last_name": "User",
            "locale": "en-US",
            "preferred_language": "en",
            "preferred_voice_id": "aura-2-thalia-en",
            "style_profile": {
                "aesthetics": ["showoff", "black-tie"],
                "color_palette": ["black", "white", "red", "yellow", "green", "pink"],
                "avoid": ["dark"],
                "body_notes": None,
                "budget_monthly_cents": 25000,
            },
            "cultural_context": {
                "region": "US",
                "religion": None,
                "dress_conservativeness": "moderate",
            },
            "roles": ["user"],
            "is_demo": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
        {
            "id": DEMO_USER_IDS[4],
            "email": "demo5@dressapp.co",
            "display_name": "Demo User 5",
            "first_name": "Demo5",
            "last_name": "User",
            "locale": "en-US",
            "preferred_language": "en",
            "preferred_voice_id": "aura-2-thalia-en",
            "style_profile": {
                "aesthetics": ["minimalist", "smart-casual"],
                "color_palette": ["black", "white", "red"],
                "avoid": ["colorful"],
                "body_notes": None,
                "budget_monthly_cents": 25000,
            },
            "cultural_context": {
                "region": "US",
                "religion": None,
                "dress_conservativeness": "moderate",
            },
            "roles": ["user"],
            "is_demo": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
    ]
    for u in demo_users:
        await db.users.update_one({"id": u["id"]}, {"$set": u}, upsert=True)
    print(f"  ✔ users: {len(demo_users)}")

    pros = [
        {
            "id": DEMO_PRO_IDS[0],
            "email": "stylist@dressapp.co",
            "display_name": "Maya Cohen",
            "first_name": "Maya",
            "last_name": "Cohen",
            "avatar_url": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200",
            "locale": "en-US",
            "preferred_language": "en",
            "preferred_voice_id": "aura-2-thalia-en",
            "roles": ["user"],
            "is_demo": True,
            "professional": {
                "is_professional": True,
                "approval_status": "approved",
                "title": "Personal Stylist",
                "profession": "Stylist",
                "bio": "Helping creatives build a wardrobe that travels well — capsule first, statement second.",
                "city": "Tel Aviv",
                "country": "IL",
                "website": "https://example.com",
                "specialties": ["capsule wardrobe", "minimalist", "travel"],
                "years_experience": 8,
                "rating": 4.9,
                "reviews_count": 47,
            },
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
        {
            "id": DEMO_PRO_IDS[1],
            "email": "tailor@dressapp.co",
            "display_name": "James Reid",
            "first_name": "James",
            "last_name": "Reid",
            "avatar_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200",
            "locale": "en-US",
            "preferred_language": "en",
            "preferred_voice_id": "aura-2-thalia-en",
            "roles": ["user"],
            "is_demo": True,
            "professional": {
                "is_professional": True,
                "approval_status": "approved",
                "title": "Master Tailor",
                "profession": "Tailor",
                "bio": "Bespoke alterations and made-to-measure suits. 15+ years on Savile Row.",
                "city": "London",
                "country": "GB",
                "specialties": ["alterations", "bespoke suits", "menswear"],
                "years_experience": 15,
                "rating": 4.8,
                "reviews_count": 92,
            },
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
        {
            "id": DEMO_PRO_IDS[2],
            "email": "designer@dressapp.co",
            "display_name": "Sofia Marchetti",
            "first_name": "Sofia",
            "last_name": "Marchetti",
            "avatar_url": "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200",
            "locale": "en-US",
            "preferred_language": "en",
            "preferred_voice_id": "aura-2-thalia-en",
            "roles": ["user"],
            "is_demo": True,
            "professional": {
                "is_professional": True,
                "approval_status": "approved",
                "title": "Fashion Designer",
                "profession": "Fashion designer",
                "bio": "Independent womenswear label focused on responsibly-sourced fabrics.",
                "city": "Milan",
                "country": "IT",
                "specialties": ["sustainable fashion", "womenswear", "made-to-order"],
                "years_experience": 6,
                "rating": 4.7,
                "reviews_count": 31,
            },
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
    ]
    for p in pros:
        await db.users.update_one({"id": p["id"]}, {"$set": p}, upsert=True)
    print(f"  ✔ professionals: {len(pros)}")


async def seed_listings(db) -> None:
    """Eight marketplace listings, varied categories + price points."""
    catalog = [
        {
            "title": "Vintage Levi's 501 Jeans",
            "category": "bottoms",
            "price": 4800,
            "image": "https://images.unsplash.com/photo-1542272604-787c3835535d?w=600",
            "city": "Brooklyn",
            "country": "US",
        },
        {
            "title": "Cream Cashmere Crew Sweater",
            "category": "tops",
            "price": 12000,
            "image": "https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=600",
            "city": "Tel Aviv",
            "country": "IL",
        },
        {
            "title": "Black Wool Overcoat",
            "category": "outerwear",
            "price": 22000,
            "image": "https://images.unsplash.com/photo-1539109136881-3be0616acf4b?w=600",
            "city": "London",
            "country": "GB",
        },
        {
            "title": "Linen Midi Dress",
            "category": "dresses",
            "price": 8900,
            "image": "https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=600",
            "city": "Lisbon",
            "country": "PT",
        },
        {
            "title": "White Leather Sneakers",
            "category": "shoes",
            "price": 6500,
            "image": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600",
            "city": "Berlin",
            "country": "DE",
        },
        {
            "title": "Silk Slip Camisole",
            "category": "tops",
            "price": 5400,
            "image": "https://images.unsplash.com/photo-1551803091-e20673f15770?w=600",
            "city": "Paris",
            "country": "FR",
        },
        {
            "title": "Tailored Houndstooth Blazer",
            "category": "outerwear",
            "price": 14500,
            "image": "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=600",
            "city": "Milan",
            "country": "IT",
        },
        {
            "title": "Suede Chelsea Boots",
            "category": "shoes",
            "price": 11800,
            "image": "https://images.unsplash.com/photo-1605812860427-4024433a70fd?w=600",
            "city": "Madrid",
            "country": "ES",
        },
    ]
    sellers = [DEMO_USER_IDS[0], DEMO_PRO_IDS[0], DEMO_PRO_IDS[2]]
    for i, item in enumerate(catalog):
        listing = {
            "id": DEMO_LISTING_IDS[i],
            "seller_id": sellers[i % len(sellers)],
            "source": "DressApp",
            "mode": "sell",
            "title": item["title"],
            "description": f"{item['title']} in excellent pre-loved condition. Curated by DressApp.",
            "category": item["category"],
            "size": "M",
            "condition": "good",
            "images": [item["image"]],
            "ships_to": ["US", "EU", "IL"],
            "financial_metadata": {
                "list_price_cents": item["price"],
                "currency": "USD",
                "platform_fee_percent": 7.0,
                "platform_fee_applied_after": "stripe_processing_fee",
                "stripe_processing_fee_percent": 2.9,
                "stripe_processing_fee_fixed_cents": 30,
                "estimated_seller_net_cents": int(item["price"] * 0.91),
            },
            "status": "active",
            "views": 12 + i * 7,
            "favorites": i,
            "is_demo": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        await db.listings.update_one(
            {"id": listing["id"]}, {"$set": listing}, upsert=True
        )
    print(f"  ✔ listings: {len(catalog)}")


async def seed_closet(db) -> None:
    """A few items in the demo user's closet so the closet view isn't empty."""
    items = [
        {
            "title": "Navy Linen Shirt",
            "category": "tops",
            "color": "navy",
            "image": "https://images.unsplash.com/photo-1603252109303-2751441dd157?w=600",
        },
        {
            "title": "Olive Cargo Trousers",
            "category": "bottoms",
            "color": "olive",
            "image": "https://images.unsplash.com/photo-1473966968600-fa801b56a6f5?w=600",
        },
        {
            "title": "Cream Trench Coat",
            "category": "outerwear",
            "color": "cream",
            "image": "https://images.unsplash.com/photo-1539533113208-f6df8cc8b543?w=600",
        },
        {
            "title": "Black Turtleneck",
            "category": "tops",
            "color": "black",
            "image": "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?w=600",
        },
        {
            "title": "White Canvas Sneakers",
            "category": "shoes",
            "color": "white",
            "image": "https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77?w=600",
        },
    ]
    for i, it in enumerate(items):
        doc = {
            "id": DEMO_CLOSET_IDS[i],
            "user_id": DEMO_USER_IDS[0],
            "source": "Private",
            "title": it["title"],
            "name": it["title"],
            "category": it["category"],
            "color": it["color"],
            "season": ["spring", "fall"],
            "marketplace_intent": "own",
            "currency": "USD",
            "wear_count": 0,
            "tags": ["demo"],
            "original_image_url": it["image"],
            "segmented_image_url": it["image"],
            "is_demo": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        await db.closet_items.update_one(
            {"id": doc["id"]}, {"$set": doc}, upsert=True
        )
    print(f"  ✔ closet items: {len(items)}")


async def seed_campaigns(db) -> None:
    """Three promo campaigns for the homepage ticker."""
    campaigns = [
        {
            "id": DEMO_CAMPAIGN_IDS[0],
            "owner_id": DEMO_PRO_IDS[0],
            "name": "Summer Capsule Wardrobe Workshop",
            "profession": "Stylist",
            "creative": {
                "headline": "Build your summer capsule with Maya",
                "body": "1-on-1 virtual styling. 20% off for first 10 bookings.",
                "image_url": "https://images.unsplash.com/photo-1469334031218-e382a71b716b?w=400",
                "cta_label": "Book a session",
                "cta_url": "https://dressapp.co/experts",
            },
            "daily_budget_cents": 5000,
            "bid_cents": 50,
            "start_date": _iso_in_days(-3),
            "end_date": _iso_in_days(60),
            "target_country": None,
            "target_region": None,
            "status": "active",
            "currency": "USD",
            "impressions": 142,
            "clicks": 18,
            "spent_cents": 0,
            "is_demo": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
        {
            "id": DEMO_CAMPAIGN_IDS[1],
            "owner_id": DEMO_PRO_IDS[1],
            "name": "Bespoke Suit — Spring Collection",
            "profession": "Tailor",
            "creative": {
                "headline": "Made-to-measure suits — Savile Row craft",
                "body": "Three fittings, six weeks. Free first consultation.",
                "image_url": "https://images.unsplash.com/photo-1593030761757-71fae45fa0e7?w=400",
                "cta_label": "See collection",
                "cta_url": "https://dressapp.co/experts",
            },
            "daily_budget_cents": 8000,
            "bid_cents": 80,
            "start_date": _iso_in_days(-7),
            "end_date": _iso_in_days(45),
            "target_country": "GB",
            "target_region": None,
            "status": "active",
            "currency": "USD",
            "impressions": 87,
            "clicks": 9,
            "spent_cents": 0,
            "is_demo": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
        {
            "id": DEMO_CAMPAIGN_IDS[2],
            "owner_id": DEMO_PRO_IDS[2],
            "name": "Sustainable SS26 Drop",
            "profession": "Fashion designer",
            "creative": {
                "headline": "New SS26 collection — responsibly sourced",
                "body": "Linen, hemp, deadstock silks. Made-to-order in Milan.",
                "image_url": "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=400",
                "cta_label": "Shop the drop",
                "cta_url": "https://dressapp.co/marketplace",
            },
            "daily_budget_cents": 3000,
            "bid_cents": 30,
            "start_date": _iso_in_days(-1),
            "end_date": _iso_in_days(30),
            "target_country": None,
            "target_region": None,
            "status": "active",
            "currency": "USD",
            "impressions": 56,
            "clicks": 11,
            "spent_cents": 0,
            "is_demo": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
    ]
    for c in campaigns:
        await db.ad_campaigns.update_one({"id": c["id"]}, {"$set": c}, upsert=True)
    print(f"  ✔ promo campaigns: {len(campaigns)}")


async def seed_trends(db) -> None:
    """One trend per bucket so the home view has cards."""
    today = datetime.now(timezone.utc).date().isoformat()
    cards = [
        {
            "bucket": "ss26-runway",
            "label": "Runway",
            "headline": "Sheer layering becomes wearable",
            "summary": (
                "SS26 runways doubled down on sheer organza shirts over crisp tanks — "
                "the move is wearable layering, not red-carpet drama."
            ),
            "image_url": "https://images.unsplash.com/photo-1558769132-cb1aea458c5e?w=600",
        },
        {
            "bucket": "street",
            "label": "Street",
            "headline": "Wide-leg jeans + boat shoes",
            "summary": (
                "Across Copenhagen and Tokyo, the most-photographed pairing this season "
                "is high-rise wide-leg denim with leather boat shoes — preppy, but loose."
            ),
            "image_url": "https://images.unsplash.com/photo-1483985988355-763728e1935b?w=600",
        },
        {
            "bucket": "sustainability",
            "label": "Sustainability",
            "headline": "Resale becomes the default",
            "summary": (
                "Major brands now bake resale into product pages. Implication for shoppers: "
                "before buying new, scan for the same item second-hand at 40-60% off."
            ),
            "image_url": "https://images.unsplash.com/photo-1521334884684-d80222895322?w=600",
        },
        {
            "bucket": "influencers",
            "label": "Influencers",
            "headline": "Pernille Teisbaek's quiet luxury",
            "summary": (
                "Copenhagen's Pernille Teisbaek keeps shaping how northern Europe dresses — "
                "elevated basics, hero outerwear, zero logos. Easy to copy with what you own."
            ),
            "image_url": "https://images.unsplash.com/photo-1487412720507-e7ab37603c6f?w=600",
        },
    ]
    for c in cards:
        doc = {
            "id": f"demo-trend-{c['bucket']}",
            "bucket": c["bucket"],
            "label": c["label"],
            "date": today,
            "language": "en",
            "headline": c["headline"],
            "summary": c["summary"],
            "image_url": c["image_url"],
            "source": "demo-seed",
            "is_demo": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        await db.trend_reports.update_one(
            {"bucket": doc["bucket"], "date": today, "language": "en"},
            {"$set": doc},
            upsert=True,
        )
    print(f"  ✔ trend cards: {len(cards)}")


async def main() -> None:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise SystemExit("MONGO_URL and DB_NAME env vars are required.")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"Seeding demo data into '{db_name}' …")
    await seed_user(db)
    await seed_listings(db)
    await seed_closet(db)
    await seed_campaigns(db)
    await seed_trends(db)
    print("Done. ✨")
    print(
        "\nDemo identifiers (re-running this script is idempotent):\n"
        f"  users:         {len(DEMO_USER_IDS)} (demo1..5@dressapp.co)\n"
        f"  professionals: {len(DEMO_PRO_IDS)}\n"
        f"  listings:      {len(DEMO_LISTING_IDS)}\n"
        f"  closet items:  {len(DEMO_CLOSET_IDS)}\n"
        f"  campaigns:     {len(DEMO_CAMPAIGN_IDS)}\n"
        f"  trend cards:   4\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
