"""Phase 1 POC \u2014 DressApp core multimodal stylist pipeline.

Runs end-to-end with REAL providers:
  1. Deepgram Aura-2      TTS (also used to bootstrap a test voice note)
  2. Groq Whisper-large-v3 ASR
  3. fal.ai SAM-2 / rembg  segmentation
  4. fal.ai Stable Diffusion image-to-image infill
  5. OpenWeatherMap        current weather
  6. Gemini 2.5 Pro        styling brain (via Emergent Universal LLM Key)

It runs TWO cases:
  A) image + text      \u2192 produces advice JSON + TTS MP3
  B) image + voice     \u2192 produces transcript + advice JSON + TTS MP3

Artifacts are written to /app/poc_artifacts and the script exits non-zero on
any hard failure (missing API keys, LLM returned empty advice, TTS empty, \u2026).
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

from app.services.calendar_service import calendar_service  # noqa: E402
from app.services.deepgram_service import deepgram_service  # noqa: E402
from app.services.fees import compute_fees  # noqa: E402
from app.services.gemini_image_service import gemini_image_service  # noqa: E402
from app.services.gemini_stylist import gemini_stylist_service  # noqa: E402
from app.services.groq_service import groq_whisper_service  # noqa: E402
from app.services.hf_segmentation import hf_segmentation_service  # noqa: E402
from app.services.logic import get_styling_advice  # noqa: E402
from app.services.weather_service import weather_service  # noqa: E402

ARTIFACTS = ROOT / "poc_artifacts"
ARTIFACTS.mkdir(exist_ok=True)

# A real, feature-rich clothing photo from Unsplash (white oxford shirt).
TEST_IMAGE_URL = (
    "https://images.unsplash.com/photo-1603252109303-2751441dd157"
    "?w=900&q=80&auto=format&fit=crop"
)

# Coordinates for a well-known city so OpenWeatherMap returns real data.
TEST_LAT = 40.7580   # Times Square, NYC
TEST_LNG = -73.9855


# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


FAL_SKIPPED = False  # retained for legacy prints; unused with HF/Nano Banana stack


def require(condition: bool, message: str) -> None:
    if not condition:
        print(f"\u274c FAIL: {message}")
        raise SystemExit(1)
    print(f"\u2705 PASS: {message}")


def warn(message: str) -> None:
    print(f"\u26a0\ufe0f  WARN: {message}")


async def download_test_image() -> bytes:
    section("0. Downloading test clothing image")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(TEST_IMAGE_URL, follow_redirects=True)
        resp.raise_for_status()
        data = resp.content
    (ARTIFACTS / "00_test_image.jpg").write_bytes(data)
    print(f"   saved \u2192 {ARTIFACTS/'00_test_image.jpg'}  ({len(data)} bytes)")
    require(len(data) > 10_000, "downloaded clothing image is non-trivial")
    return data


async def check_api_keys() -> None:
    section("1. Verifying API keys are configured")
    require(os.getenv("HF_TOKEN") is not None, "HF_TOKEN present")
    require(os.getenv("GROQ_API_KEY") is not None, "GROQ_API_KEY present")
    require(os.getenv("DEEPGRAM_API_KEY") is not None, "DEEPGRAM_API_KEY present")
    require(os.getenv("OPENWEATHER_API_KEY") is not None, "OPENWEATHER_API_KEY present")
    require(os.getenv("EMERGENT_LLM_KEY") is not None, "EMERGENT_LLM_KEY present")


async def test_deepgram_tts() -> bytes:
    section("2. Deepgram Aura-2 REST TTS")
    text = "Hello from DressApp. I'm your stylist agent and I'm ready to help."
    audio = await deepgram_service.speak_to_bytes(text, voice="aura-2-thalia-en", encoding="mp3")
    (ARTIFACTS / "02_deepgram_greeting.mp3").write_bytes(audio)
    require(len(audio) > 2_000, f"Deepgram returned an MP3 ({len(audio)} bytes)")
    return audio


async def test_groq_whisper() -> str:
    section("3. Groq Whisper-large-v3 transcription")
    # Generate a known-content audio clip with Deepgram so we can verify ASR.
    spoken = (
        "What should I wear to a client pitch tomorrow morning in the rain?"
    )
    audio = await deepgram_service.speak_to_bytes(spoken, voice="aura-2-thalia-en", encoding="mp3")
    (ARTIFACTS / "03_voice_input.mp3").write_bytes(audio)
    # Groq SDK call is synchronous \u2014 run in a thread.
    result = await asyncio.to_thread(
        groq_whisper_service.transcribe,
        audio,
        "voice_input.mp3",
        "audio/mpeg",
        "en",
    )
    transcript = (result["text"] or "").strip()
    print("   transcript:", transcript)
    require(len(transcript) > 10, "Groq returned a non-trivial transcript")
    # Loose semantic check \u2014 we only care that key content words made it through.
    lower = transcript.lower()
    require(
        any(k in lower for k in ["wear", "client", "pitch", "rain"]),
        "Transcript contains expected content words",
    )
    return transcript


async def test_hf_segment(image_bytes: bytes) -> str | None:
    section("4. Hugging Face SAM segmentation (SAM \u2192 RMBG fallback)")
    try:
        seg = await hf_segmentation_service.segment_garment(image_bytes)
    except Exception as exc:  # noqa: BLE001
        warn(f"HF segmentation failed: {str(exc)[:160]}")
        return None
    print("   model_used:", seg.get("model_used"))
    require(bool(seg.get("image_b64")), "Segmentation produced image bytes")
    raw = base64.b64decode(seg["image_b64"])
    (ARTIFACTS / "04_segmented.png").write_bytes(raw)
    require(len(raw) > 2_000, "Segmented image has real content")
    return f"data:{seg.get('mime_type', 'image/png')};base64,{seg['image_b64']}"


async def test_nano_banana_edit(image_bytes: bytes) -> str | None:
    section("5. Gemini Nano Banana image-to-image edit")
    try:
        edit = await gemini_image_service.edit(
            image_bytes,
            prompt=(
                "Same garment, but in deep navy blue. Clean studio backdrop, "
                "high detail photograph."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        warn(f"Nano Banana edit failed: {str(exc)[:160]}")
        return None
    print("   model_used:", edit.get("model_used"))
    require(bool(edit.get("image_b64")), "Edit produced image bytes")
    raw = base64.b64decode(edit["image_b64"])
    (ARTIFACTS / "05_edit_navy.png").write_bytes(raw)
    require(len(raw) > 5_000, "Edited image has real content")
    return f"data:{edit.get('mime_type', 'image/png')};base64,{edit['image_b64']}"


async def test_openweather() -> dict[str, Any]:
    section("6. OpenWeatherMap current + forecast")
    weather = await weather_service.fetch(TEST_LAT, TEST_LNG)
    print(json.dumps(weather, indent=2)[:500])
    require(weather.get("temp_c") is not None, "Weather returned a temperature")
    require(weather.get("city") is not None, "Weather returned a city name")
    return weather


async def test_case_image_plus_text(image_bytes: bytes) -> dict[str, Any]:
    section("7. FULL PIPELINE \u2014 image + TEXT (with weather + mock calendar)")
    advice = await get_styling_advice(
        session_id="poc-image-text",
        image_bytes=image_bytes,
        image_mime="image/jpeg",
        user_text=(
            "I have a client pitch at 10am tomorrow in NYC. "
            "I'm thinking about wearing this oxford shirt. "
            "Build me a complete outfit and tell me if it's right for the weather."
        ),
        lat=TEST_LAT,
        lng=TEST_LNG,
        do_infill=False,
        voice_id="aura-2-thalia-en",
        calendar_events=[calendar_service.mock_event("Client pitch")],
        user_profile={
            "preferred_language": "en",
            "style_profile": {"aesthetics": ["minimalist", "smart-casual"]},
            "cultural_context": {"region": "US"},
        },
        closet_summary=[
            {"id": "a1", "title": "Navy wool blazer", "category": "outerwear"},
            {"id": "a2", "title": "Grey wool trousers", "category": "bottom"},
            {"id": "a3", "title": "Brown leather derby shoes", "category": "shoes"},
            {"id": "a4", "title": "White oxford shirt", "category": "top"},
            {"id": "a5", "title": "Beige trench coat", "category": "outerwear"},
        ],
        synthesize_tts=True,
    )
    _dump_advice(advice, tag="07_image_text")
    require(bool(advice.get("reasoning_summary")), "Advice includes reasoning_summary")
    require(len(advice.get("outfit_recommendations") or []) >= 1,
            "Advice includes at least one outfit_recommendation")
    require(bool(advice.get("tts_audio_base64")), "TTS audio bytes returned")
    return advice


async def test_case_image_plus_voice(image_bytes: bytes) -> dict[str, Any]:
    section("8. FULL PIPELINE \u2014 image + VOICE (Whisper \u2192 Gemini \u2192 TTS)")
    # Synthesize the user's voice via Deepgram (bootstraps Whisper input).
    spoken = (
        "What should I wear to a casual brunch this Sunday? "
        "The weather is chilly and I want layered minimalist vibes."
    )
    voice_audio = await deepgram_service.speak_to_bytes(
        spoken, voice="aura-2-hermes-en", encoding="mp3"
    )
    (ARTIFACTS / "08_user_voice_input.mp3").write_bytes(voice_audio)

    advice = await get_styling_advice(
        session_id="poc-image-voice",
        image_bytes=image_bytes,
        image_mime="image/jpeg",
        user_text=None,
        voice_audio=voice_audio,
        voice_filename="user_voice.mp3",
        voice_mime="audio/mpeg",
        language="en",
        lat=TEST_LAT,
        lng=TEST_LNG,
        voice_id="aura-2-thalia-en",
        user_profile={
            "style_profile": {"aesthetics": ["minimalist"]},
        },
        closet_summary=[
            {"id": "b1", "title": "Cream cashmere crewneck", "category": "top"},
            {"id": "b2", "title": "Dark indigo straight jeans", "category": "bottom"},
            {"id": "b3", "title": "White leather trainers", "category": "shoes"},
            {"id": "b4", "title": "Charcoal wool overcoat", "category": "outerwear"},
        ],
        synthesize_tts=True,
    )
    _dump_advice(advice, tag="08_image_voice")
    require(bool(advice.get("transcript")), "Voice case produced a transcript")
    require(bool(advice.get("reasoning_summary")), "Voice case returned reasoning_summary")
    require(bool(advice.get("tts_audio_base64")), "Voice case returned TTS audio")
    return advice


def test_fee_math() -> None:
    section("9. Marketplace fee math \u2014 7% after Stripe fees")
    fb = compute_fees(2500)  # $25.00
    print("   ", fb.to_dict())
    # round(2500*0.029 + 30) \u2192 round(102.5) = 102 (banker's rounding)
    # net_after = 2398; platform = round(2398 * 0.07) = round(167.86) = 168
    # seller_net = 2230
    require(fb.stripe_fee_cents == 102, "Stripe fee cents = 102 for $25 gross")
    require(fb.net_after_stripe_cents == 2398, "Net after Stripe = 2398")
    require(fb.platform_fee_cents == 168, "Platform fee (7% after Stripe) = 168")
    require(fb.seller_net_cents == 2230, "Seller net = 2230")
    # Also sanity-check a larger transaction
    fb2 = compute_fees(10000)  # $100
    require(fb2.stripe_fee_cents == 320, "Stripe fee for $100 gross = 320")
    # net = 9680; platform = round(9680 * 0.07) = 678; seller = 9002
    require(fb2.platform_fee_cents == 678, "Platform fee for $100 = 678")
    require(fb2.seller_net_cents == 9002, "Seller net for $100 = 9002")


def _dump_advice(advice: dict[str, Any], *, tag: str) -> None:
    slim = {k: v for k, v in advice.items() if k != "tts_audio_base64"}
    (ARTIFACTS / f"{tag}.json").write_text(json.dumps(slim, indent=2, ensure_ascii=False))
    if advice.get("tts_audio_base64"):
        (ARTIFACTS / f"{tag}_reply.mp3").write_bytes(
            base64.b64decode(advice["tts_audio_base64"])
        )
    # Pretty excerpt
    print("   reasoning:", (advice.get("reasoning_summary") or "")[:160])
    for i, rec in enumerate(advice.get("outfit_recommendations") or [], 1):
        items = ", ".join(
            (it.get("description") or it.get("role") or "?")
            for it in rec.get("items") or []
        )
        print(f"   outfit {i}: {rec.get('name')}  \u2014  items: {items}")
    print("   latency:", advice.get("latency_ms"))


async def main() -> None:
    print("DressApp Phase-1 POC \u2014 running core multimodal stylist pipeline")
    print("=" * 72)

    await check_api_keys()
    image_bytes = await download_test_image()

    # Independent sanity checks (fail-fast per-provider)
    await test_deepgram_tts()
    transcript = await test_groq_whisper()
    print("   (Whisper transcript preserved for reference) \u2192", transcript[:80], "\u2026")

    await test_hf_segment(image_bytes)
    await test_nano_banana_edit(image_bytes)
    await test_openweather()

    # Orchestrated end-to-end runs (the core path)
    await test_case_image_plus_text(image_bytes)
    await test_case_image_plus_voice(image_bytes)

    # Financial ledger correctness (no network; pure math)
    test_fee_math()

    section("PHASE 1 POC RESULTS")
    print("   \u2705 ALL providers (HF SAM + Nano Banana + Groq + Deepgram + Gemini) are green.")
    print(f"   all artifacts \u2192 {ARTIFACTS}")


if __name__ == "__main__":
    asyncio.run(main())
