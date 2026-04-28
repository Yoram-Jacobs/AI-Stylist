"""Production LLM pipeline health check.

Run from inside the backend container:
    docker compose exec backend python scripts/diagnose_llm.py

Outputs the health of every link in the chain:
  1. Keys loaded into the container
  2. Direct Gemini chat (Stylist path)
  3. Direct Gemini vision (The Eyes path)
  4. Clothing parser + rembg local models
  5. Filesystem cache volumes
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback

# Make the `app` package importable when run as a script.
sys.path.insert(0, "/app/backend")


def print_header(title: str) -> None:
    print("\n" + "═" * 60)
    print(f"  {title}")
    print("═" * 60)


def mask(val: str | None) -> str:
    if not val:
        return "(empty)"
    return f"len={len(val):3d}  prefix={val[:7]!r}"


# ─── 1) Environment keys ─────────────────────────────────────────
def check_keys() -> None:
    print_header("1) Environment keys (masked)")
    for k in [
        "EMERGENT_LLM_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "HF_TOKEN",
        "GROQ_API_KEY",
        "DEEPGRAM_API_KEY",
        "OPENWEATHER_API_KEY",
        "MONGO_URL",
    ]:
        print(f"  {k:22s} {mask(os.environ.get(k))}")


# ─── 2) Stylist chat smoke test ─────────────────────────────────
async def check_stylist() -> None:
    print_header("2) Gemini Stylist (direct chat via litellm)")
    try:
        from app.services.gemini_stylist import gemini_stylist_service
    except Exception as e:  # noqa: BLE001
        print(f"  IMPORT FAIL: {type(e).__name__}: {e}")
        return
    if gemini_stylist_service is None:
        print("  service is None — check GEMINI_API_KEY / EMERGENT_LLM_KEY")
        return
    print(
        f"  service={type(gemini_stylist_service).__name__} "
        f"model={gemini_stylist_service.model} "
        f"key_prefix={gemini_stylist_service.api_key[:7]!r}"
    )
    try:
        out = await gemini_stylist_service.advise(
            session_id="diagnose-stylist",
            user_text='Return exactly this JSON: {"reasoning_summary": "diag ok", "outfit_recommendations": [], "shopping_suggestions": [], "do_dont": [], "spoken_reply": "ok"}',
            image_base64=None,
        )
        print(f"  OK — spoken_reply={out.get('spoken_reply')!r}")
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL: {type(e).__name__}: {str(e)[:500]}")
        traceback.print_exc(limit=2)


# ─── 3) The Eyes vision smoke test ──────────────────────────────
def _make_tiny_jpeg() -> bytes:
    """Generate a 32x32 white JPEG at call time — avoids hex-literal typos."""
    import io
    from PIL import Image

    img = Image.new("RGB", (32, 32), (245, 245, 245))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


async def check_eyes() -> None:
    print_header("3) The Eyes (Gemini vision smoke test)")
    try:
        from app.services.garment_vision import garment_vision_service
    except Exception as e:  # noqa: BLE001
        print(f"  IMPORT FAIL: {type(e).__name__}: {e}")
        return
    if garment_vision_service is None:
        print("  service is None")
        return
    print(
        f"  model={garment_vision_service.model} "
        f"provider={garment_vision_service.provider} "
        f"detect_model={garment_vision_service.detect_model}"
    )
    tiny = _make_tiny_jpeg()
    try:
        out = await garment_vision_service.analyze(tiny)
        print(
            f"  OK — title={out.get('title')!r} "
            f"category={out.get('category')!r} "
            f"used_model={out.get('model_used')!r}"
        )
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL: {type(e).__name__}: {str(e)[:500]}")
        traceback.print_exc(limit=2)


# ─── 4) Local segmentation + rembg ──────────────────────────────
def check_local_vision() -> None:
    print_header("4) Local vision stack (SegFormer + rembg)")
    try:
        from app.config import settings
    except Exception as e:  # noqa: BLE001
        print(f"  config import FAIL: {e}")
        return
    print(f"  USE_LOCAL_CLOTHING_PARSER = {settings.USE_LOCAL_CLOTHING_PARSER}")
    print(f"  USE_CLOTHING_PARSER       = {settings.USE_CLOTHING_PARSER}")
    print(f"  AUTO_MATTE_CROPS          = {settings.AUTO_MATTE_CROPS}")
    print(f"  rembg model               = {settings.BACKGROUND_MATTING_REMBG_MODEL}")
    print(f"  clothing parser model     = {settings.CLOTHING_PARSER_MODEL}")
    try:
        from app.services import clothing_parser  # noqa: F401
        print("  clothing_parser import   OK")
    except Exception as e:  # noqa: BLE001
        print(f"  clothing_parser import   FAIL: {repr(e)[:300]}")
    try:
        from app.services import background_matting  # noqa: F401
        print("  background_matting impo  OK")
    except Exception as e:  # noqa: BLE001
        print(f"  background_matting impo  FAIL: {repr(e)[:300]}")


# ─── 5) Cache volumes ──────────────────────────────────────────
def check_caches() -> None:
    print_header("5) Model cache volumes")
    for path in (
        "/models/huggingface",
        "/models/u2net",
        os.path.expanduser("~/.u2net"),
        "/root/.cache/huggingface",
    ):
        if not os.path.exists(path):
            print(f"  {path:40s} MISSING")
            continue
        size = 0
        files = 0
        for root, _, fnames in os.walk(path):
            for f in fnames:
                try:
                    size += os.path.getsize(os.path.join(root, f))
                    files += 1
                except OSError:
                    pass
        print(f"  {path:40s} exists  files={files:4d}  size={size/1024/1024:7.1f} MB")


# ─── Run all ──────────────────────────────────────────────────
async def main() -> None:
    check_keys()
    await check_stylist()
    await check_eyes()
    check_local_vision()
    check_caches()
    print("\nDone.\n")


if __name__ == "__main__":
    asyncio.run(main())
