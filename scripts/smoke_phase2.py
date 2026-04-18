"""Quick end-to-end smoke test for Phase 2 backend.

Runs against the live FastAPI server on localhost:8001 and exercises every
major Phase 2 flow: dev-bypass auth, user profile patch, closet CRUD, listing
CRUD + fee preview, transaction creation, and the authenticated stylist route
with memory persistence.
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path

import httpx

BASE = "http://localhost:8001/api/v1"
IMG_PATH = Path("/app/poc_artifacts/00_test_image.jpg")


def step(n: int, title: str) -> None:
    print(f"\n--- [{n}] {title} ---")


def must(cond: bool, msg: str) -> None:
    if not cond:
        print(f"❌ {msg}")
        sys.exit(1)
    print(f"✅ {msg}")


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=120.0) as c:
        step(1, "dev-bypass login")
        r = await c.post("/auth/dev-bypass")
        must(r.status_code == 200, f"dev-bypass status 200 (got {r.status_code})")
        tok = r.json()["access_token"]
        user = r.json()["user"]
        h = {"Authorization": f"Bearer {tok}"}
        print("   user_id:", user["id"])

        step(2, "GET /users/me")
        r = await c.get("/users/me", headers=h)
        must(r.status_code == 200, "GET /users/me = 200")
        must(r.json()["email"] == "dev@dressapp.io", "email matches")

        step(3, "PATCH /users/me (style profile)")
        r = await c.patch(
            "/users/me",
            headers=h,
            json={
                "preferred_voice_id": "aura-2-hermes-en",
                "style_profile": {
                    "aesthetics": ["minimalist", "smart-casual"],
                    "color_palette": ["navy", "ivory", "charcoal"],
                    "avoid": ["neon"],
                },
                "home_location": {"lat": 40.758, "lng": -73.9855, "city": "New York"},
            },
        )
        must(r.status_code == 200, "patch profile = 200")
        must(
            r.json()["preferred_voice_id"] == "aura-2-hermes-en",
            "voice preference stored",
        )

        step(4, "POST /closet (2 items)")
        img_b64 = base64.b64encode(IMG_PATH.read_bytes()).decode("ascii") if IMG_PATH.exists() else None
        items = [
            {
                "category": "top",
                "title": "White Oxford Shirt",
                "brand": "Uniqlo",
                "color": "white",
                "formality": "smart-casual",
                "tags": ["oxford", "office"],
                "original_image_url": "https://images.unsplash.com/photo-1603252109303-2751441dd157?w=900&q=80",
            },
            {
                "category": "bottom",
                "title": "Grey Wool Trousers",
                "color": "grey",
                "formality": "business",
                "tags": ["wool", "tailored"],
            },
        ]
        closet_ids: list[str] = []
        for it in items:
            r = await c.post("/closet", headers=h, json=it)
            must(r.status_code == 201, f"create {it['title']} = 201")
            closet_ids.append(r.json()["id"])

        step(5, "GET /closet")
        r = await c.get("/closet", headers=h)
        must(r.status_code == 200, "list closet = 200")
        must(r.json()["total"] >= 2, f"at least 2 items (got {r.json()['total']})")

        step(6, "GET /listings/fee-preview?list_price_cents=2500")
        r = await c.get("/listings/fee-preview?list_price_cents=2500")
        must(r.status_code == 200, "fee-preview = 200")
        fp = r.json()
        must(
            fp["stripe_fee_cents"] == 102 and fp["platform_fee_cents"] == 168,
            f"fee math correct: {fp}",
        )

        step(7, "POST /listings (link to closet item #1)")
        r = await c.post(
            "/listings",
            headers=h,
            json={
                "closet_item_id": closet_ids[0],
                "source": "Shared",
                "mode": "sell",
                "title": "White Oxford Shirt — lightly worn",
                "description": "Worn twice, smoke-free home.",
                "category": "top",
                "size": "M",
                "condition": "like_new",
                "images": ["https://images.unsplash.com/photo-1603252109303-2751441dd157?w=900"],
                "list_price_cents": 2500,
                "currency": "USD",
            },
        )
        must(r.status_code == 201, f"create listing = 201 (got {r.status_code}: {r.text[:200]})")
        listing = r.json()
        must(
            listing["financial_metadata"]["estimated_seller_net_cents"] == 2230,
            "listing carries correct seller net",
        )

        step(8, "closet item source transitioned to Shared")
        r = await c.get(f"/closet/{closet_ids[0]}", headers=h)
        must(r.json()["source"] == "Shared", "source=Shared after listing")

        step(9, "GET /listings (public browse, no auth)")
        r = await c.get("/listings?source=Shared&category=top")
        must(r.status_code == 200, "browse listings = 200")
        must(r.json()["total"] >= 1, "found at least 1 Shared top listing")

        step(10, "create a buyer + POST /transactions")
        br = await c.post(
            "/auth/register",
            json={"email": "buyer1@dressapp.io", "password": "BuyerPass123!", "display_name": "Buyer One"},
        )
        # register may conflict if re-run; fall back to login
        if br.status_code == 201:
            buyer_tok = br.json()["access_token"]
        else:
            lg = await c.post(
                "/auth/login",
                json={"email": "buyer1@dressapp.io", "password": "BuyerPass123!"},
            )
            must(lg.status_code == 200, "buyer re-login works")
            buyer_tok = lg.json()["access_token"]
        bh = {"Authorization": f"Bearer {buyer_tok}"}
        r = await c.post("/transactions", headers=bh, json={"listing_id": listing["id"]})
        must(r.status_code == 201, f"create tx = 201 (got {r.status_code}: {r.text[:200]})")
        tx = r.json()
        must(tx["financial"]["seller_net_cents"] == 2230, "tx seller_net correct")
        must(tx["status"] == "pending", "tx status pending")

        step(11, "authenticated POST /stylist (text only, uses closet + weather)")
        r = await c.post(
            "/stylist",
            headers=h,
            data={
                "text": "I have a client pitch tomorrow in NYC. Build me an outfit from my closet.",
                "language": "en",
                "voice_id": "aura-2-thalia-en",
                "include_calendar": "true",
                "occasion": "Client pitch",
            },
        )
        must(r.status_code == 200, f"stylist = 200 (got {r.status_code}: {r.text[:400]})")
        advice = r.json()["advice"]
        must(len(advice["outfit_recommendations"]) >= 1, "stylist produced outfits")
        must(bool(advice.get("tts_audio_base64")), "stylist produced TTS audio")

        step(12, "GET /stylist/history shows user + assistant turns")
        r = await c.get("/stylist/history?limit=10", headers=h)
        must(r.status_code == 200, "history = 200")
        roles = [m["role"] for m in r.json()["messages"]]
        must("user" in roles and "assistant" in roles, f"both roles present: {roles}")

        print("\n🎉 Phase 2 smoke test — ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
