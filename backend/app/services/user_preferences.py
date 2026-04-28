"""User preference summarizer (Phase S — Stylist horizon expansion).

Produces a *compact* natural-language block that the Stylist injects into
its system prompt so every recommendation is grounded in who the user
actually is — sex, age, body shape, cultural rules, style aesthetics,
things to avoid, regional climate, etc.

Design goals:
  * Zero LLM round-trips — pure dict → string transformation, ~1 ms.
  * Resilient: any missing field is silently skipped; never raises.
  * Stable order so the prompt is reproducible (cache-friendly).
  * Returns ``(prompt_block, applied_keys)`` so the API can echo the
    list of preferences it actually used (transparency to the user).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


# ─── public ───────────────────────────────────────────────────
def render_user_preferences(
    user: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    """Return ``(prompt_block, applied_keys)``.

    ``applied_keys`` is a flat list of human-readable keys that were
    populated, e.g. ``["sex", "age", "body_height_cm", "region",
    "dress_conservativeness", "aesthetics"]``. The frontend can show
    this in a tooltip so the user understands why the Stylist made a
    given recommendation.
    """
    if not user:
        return "", []

    lines: list[str] = []
    applied: list[str] = []

    # --- identity ---
    sex = (user.get("sex") or "").lower() or None
    if sex in {"male", "female"}:
        lines.append(f"- Sex: {sex}")
        applied.append("sex")

    age = _compute_age(user.get("date_of_birth"))
    if age is not None:
        lines.append(f"- Age: {age}")
        applied.append("age")

    status = user.get("personal_status")
    if status:
        lines.append(f"- Personal status: {status}")
        applied.append("personal_status")

    # --- body ---
    bm = user.get("body_measurements") or {}
    body_bits: list[str] = []
    for src_key, label in (
        ("height_cm", "height"),
        ("height_in", "height"),
        ("weight_kg", "weight"),
        ("weight_lb", "weight"),
        ("chest_cm", "chest"),
        ("waist_cm", "waist"),
        ("hips_cm", "hips"),
        ("shoe_size_eu", "shoe size"),
        ("shoe_size_us", "shoe size"),
        ("body_type", "body type"),
        ("body_shape", "body shape"),
    ):
        v = bm.get(src_key) if isinstance(bm, dict) else None
        if v is not None and v != "":
            unit = ""
            if src_key.endswith("_cm"):
                unit = " cm"
            elif src_key.endswith("_in"):
                unit = " in"
            elif src_key.endswith("_kg"):
                unit = " kg"
            elif src_key.endswith("_lb"):
                unit = " lb"
            body_bits.append(f"{label} {v}{unit}")
            applied.append(f"body_{src_key}")
    if body_bits:
        lines.append("- Body: " + ", ".join(body_bits))

    body_notes = (user.get("style_profile") or {}).get("body_notes")
    if body_notes:
        lines.append(f"- Body notes: {body_notes}")
        applied.append("body_notes")

    # --- hair (small but useful for outfit-color matching) ---
    hair = user.get("hair") or {}
    if isinstance(hair, dict):
        hair_bits = [v for k, v in hair.items() if v and k in {"color", "length", "type"}]
        if hair_bits:
            lines.append("- Hair: " + ", ".join(str(b) for b in hair_bits))
            applied.append("hair")

    # --- cultural / regional ---
    cc = user.get("cultural_context") or {}
    if isinstance(cc, dict):
        if cc.get("region"):
            lines.append(f"- Region: {cc['region']}")
            applied.append("region")
        if cc.get("religion"):
            lines.append(f"- Religion: {cc['religion']}")
            applied.append("religion")
        if cc.get("dress_conservativeness"):
            lines.append(
                f"- Dress conservativeness: {cc['dress_conservativeness']} "
                "(prioritise modesty when this is 'high', balance when 'moderate')."
            )
            applied.append("dress_conservativeness")

    # Country (more concrete than region) — for climate + retailer hints.
    addr = user.get("address") or {}
    if isinstance(addr, dict):
        country = addr.get("country")
        city = addr.get("city")
        if country or city:
            loc = ", ".join(b for b in (city, addr.get("region"), country) if b)
            lines.append(f"- Location: {loc}")
            applied.append("address")

    # --- style profile ---
    sp = user.get("style_profile") or {}
    if isinstance(sp, dict):
        aest = sp.get("aesthetics") or []
        if aest:
            lines.append("- Style aesthetics: " + ", ".join(str(a) for a in aest[:6]))
            applied.append("aesthetics")
        palette = sp.get("color_palette") or []
        if palette:
            lines.append("- Preferred colors: " + ", ".join(str(c) for c in palette[:6]))
            applied.append("color_palette")
        avoid = sp.get("avoid") or []
        if avoid:
            lines.append("- Avoid: " + ", ".join(str(a) for a in avoid[:6]))
            applied.append("avoid")
        budget = sp.get("budget_monthly_cents")
        if budget:
            lines.append(f"- Monthly clothing budget: ~${budget / 100:.0f}")
            applied.append("budget")

    # --- locale ---
    lang = user.get("preferred_language")
    if lang:
        lines.append(f"- Preferred language: {lang}")
        applied.append("preferred_language")

    if not lines:
        return "", []

    block = (
        "USER PROFILE — apply these preferences to every recommendation; "
        "override only if the user's current message explicitly contradicts:\n"
        + "\n".join(lines)
        + "\n"
    )
    return block, applied


# ─── helpers ──────────────────────────────────────────────────
def _compute_age(dob: Any) -> int | None:
    if not dob:
        return None
    try:
        if isinstance(dob, str):
            d = datetime.fromisoformat(dob.replace("Z", "+00:00")).date()
        elif isinstance(dob, datetime):
            d = dob.date()
        elif isinstance(dob, date):
            d = dob
        else:
            return None
    except Exception:  # noqa: BLE001
        return None
    today = datetime.now(timezone.utc).date()
    years = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    if 0 < years < 130:
        return years
    return None
