"""Digital Product Passport (DPP) parser — Phase V6.

Accepts a QR-code payload (a URL *or* inline JSON) and returns a
normalised representation the closet-item form can hydrate from:

    {
        "analysis": { title, category, brand, material, colors, ... },
        "image_bytes": bytes | None,
        "image_mime":  str  | None,
        "dpp_data":    { ...full provenance doc, preserved verbatim... },
        "source_url":  str  | None,
    }

Design goals:

* Works with today's most common DPP pilots — **JSON-LD `Product` schema
  embedded in an HTML page** (roughly 90 % of observed 2026 pilots).
* Also accepts **inline JSON** encoded directly in the QR payload.
* **SSRF-safe**: when the payload is a URL we refuse private-network IPs
  before issuing the HTTP request, and we cap the response body so a
  hostile QR can't blow up memory.
* Never raises from untrusted input — returns a best-effort empty
  analysis when the payload is unparseable, so the caller can still
  show the form with a helpful error toast.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_MAX_BYTES = 2_000_000  # 2 MB ceiling on the fetched document
_FETCH_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_MAX_IMAGE_BYTES = 6_000_000  # 6 MB ceiling on any DPP image we import

# Schema.org / common DPP field aliases → our internal analysis keys.
# We map conservatively: only copy values that look like strings/numbers,
# arrays are flattened and passed through list normalisers below.
_BRAND_KEYS = ("brand", "manufacturer", "producer")
_IMAGE_KEYS = ("image", "images", "primaryImageOfPage", "logo")
_NAME_KEYS = ("name", "productName", "title", "product_name")
_CATEGORY_KEYS = ("category", "productCategory", "garmentType", "subCategory")
_COLOR_KEYS = ("color", "colour", "primaryColor")
_MATERIAL_KEYS = (
    "material",
    "materials",
    "composition",
    "materialComposition",
    "fiberContent",
    "textileComposition",
)
_COUNTRY_KEYS = ("countryOfOrigin", "origin", "madeIn", "country_of_origin")
_CARE_KEYS = ("careInstructions", "care", "careLabel", "maintenance")
_REPAIR_KEYS = ("repairInstructions", "repair", "repairGuide")
_GTIN_KEYS = ("gtin", "gtin13", "gtin14", "ean", "upc", "sku", "productID")
_CARBON_KEYS = (
    "carbonFootprint",
    "ghgEmissions",
    "co2eq",
    "carbonFootprintOfProduct",
)
_CERT_KEYS = ("certifications", "certification", "standards", "labels")


# ---------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------
async def parse_dpp(qr_payload: str) -> dict[str, Any]:
    """Normalise a raw QR payload into our draft-item shape."""
    if not qr_payload or not isinstance(qr_payload, str):
        return _empty(reason="empty_payload")

    payload = qr_payload.strip()

    # Inline JSON path — some small-data DPPs embed the whole passport
    # in the QR directly (prefix `{` or `[`).
    if payload.startswith("{") or payload.startswith("["):
        try:
            data = json.loads(payload)
        except Exception as exc:  # noqa: BLE001
            logger.info("dpp: inline JSON parse failed: %s", exc)
            return _empty(reason="inline_json_invalid")
        return await _finalise(data, source_url=None)

    # URL path.
    if not (payload.startswith("http://") or payload.startswith("https://")):
        return _empty(reason="unsupported_scheme")

    if not _is_public_url(payload):
        logger.warning("dpp: refusing non-public URL %s", payload[:120])
        return _empty(reason="url_blocked")

    try:
        async with httpx.AsyncClient(
            timeout=_FETCH_TIMEOUT, follow_redirects=True, max_redirects=5
        ) as client:
            resp = await client.get(
                payload,
                headers={
                    "Accept": "application/ld+json, application/json;q=0.9, text/html;q=0.8",
                    "User-Agent": "DressApp-DPP-Importer/1.0",
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.info("dpp: fetch failed for %s: %s", payload[:120], exc)
        return _empty(reason="fetch_failed", source_url=payload)

    if resp.status_code >= 400:
        logger.info("dpp: fetch HTTP %d for %s", resp.status_code, payload[:120])
        return _empty(reason=f"http_{resp.status_code}", source_url=payload)

    body = resp.content[:_MAX_BYTES]
    content_type = (resp.headers.get("content-type") or "").lower().split(";", 1)[0]

    data: Any = None
    if "json" in content_type:
        try:
            data = json.loads(body.decode(resp.encoding or "utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            logger.info("dpp: json parse failed: %s", exc)
    if data is None:
        # HTML — look for inline JSON-LD.
        data = _extract_jsonld_from_html(body)

    if data is None:
        return _empty(reason="no_structured_data", source_url=payload)

    return await _finalise(data, source_url=payload)


# ---------------------------------------------------------------------
# Core: walk a JSON-LD / plain-JSON document and map fields
# ---------------------------------------------------------------------
async def _finalise(raw: Any, *, source_url: str | None) -> dict[str, Any]:
    # JSON-LD documents may be wrapped in `@graph` or be arrays.
    product = _locate_product(raw)
    if product is None:
        return _empty(reason="no_product_node", source_url=source_url)

    analysis: dict[str, Any] = {}

    # --- Title / name ---
    name = _first_string(product, _NAME_KEYS)
    if name:
        analysis["title"] = name[:120]
        analysis["name"] = name[:80]

    # --- Brand ---
    brand = _first_string_from_object(product, _BRAND_KEYS)
    if brand:
        analysis["brand"] = brand[:80]

    # --- Category / sub-category ---
    category = _first_string(product, _CATEGORY_KEYS)
    if category:
        parts = [p.strip() for p in category.split(">") if p.strip()]
        if parts:
            analysis["category"] = parts[0][:60]
            if len(parts) > 1:
                analysis["sub_category"] = parts[1][:60]

    # --- Colors ---
    color_val = _first_string(product, _COLOR_KEYS)
    colors_weighted = _normalise_colors(color_val, product.get("colors"))
    if colors_weighted:
        analysis["colors"] = colors_weighted

    # --- Materials (with percentages) ---
    mats = _normalise_materials(product)
    if mats:
        analysis["fabric_materials"] = mats
        # Build a legacy flat "material" string like "80% cotton, 20% elastane"
        flat = ", ".join(
            f"{m['pct']}% {m['name']}" if m.get("pct") else m["name"]
            for m in mats[:4]
        )
        analysis["material"] = flat[:120]

    # --- DPP provenance doc (stored verbatim + normalised convenience fields) ---
    dpp_data: dict[str, Any] = {"raw": product}
    if source_url:
        dpp_data["source_url"] = source_url
    gtin = _first_string(product, _GTIN_KEYS)
    if gtin:
        dpp_data["gtin"] = gtin
    country = _first_string(product, _COUNTRY_KEYS) or _first_string_from_object(
        product, _COUNTRY_KEYS
    )
    if country:
        dpp_data["country_of_origin"] = country
    care = _coerce_str_list(product, _CARE_KEYS)
    if care:
        dpp_data["care_instructions"] = care
    repair = _coerce_str_list(product, _REPAIR_KEYS)
    if repair:
        dpp_data["repair_instructions"] = repair
    carbon = _first_scalar(product, _CARBON_KEYS)
    if carbon is not None:
        dpp_data["carbon_footprint"] = carbon
    certs = _coerce_str_list(product, _CERT_KEYS)
    if certs:
        dpp_data["certifications"] = certs
    if mats:
        dpp_data["materials_normalised"] = mats

    # --- Optional image download ---
    image_bytes: bytes | None = None
    image_mime: str | None = None
    image_url = _first_image_url(product)
    if image_url and (image_url.startswith("http://") or image_url.startswith("https://")):
        if _is_public_url(image_url):
            try:
                async with httpx.AsyncClient(
                    timeout=_FETCH_TIMEOUT, follow_redirects=True, max_redirects=5
                ) as client:
                    r2 = await client.get(
                        image_url,
                        headers={"User-Agent": "DressApp-DPP-Importer/1.0"},
                    )
                if r2.status_code == 200 and len(r2.content) <= _MAX_IMAGE_BYTES:
                    ct = (r2.headers.get("content-type") or "image/jpeg").split(";", 1)[0]
                    if ct.startswith("image/"):
                        image_bytes = r2.content
                        image_mime = ct
                        dpp_data["image_source_url"] = image_url
            except Exception as exc:  # noqa: BLE001
                logger.info("dpp: image fetch failed (%s): %s", image_url[:120], exc)

    return {
        "analysis": analysis,
        "image_bytes": image_bytes,
        "image_mime": image_mime,
        "dpp_data": dpp_data,
        "source_url": source_url,
    }


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _empty(*, reason: str, source_url: str | None = None) -> dict[str, Any]:
    return {
        "analysis": {},
        "image_bytes": None,
        "image_mime": None,
        "dpp_data": {"parse_error": reason, "source_url": source_url},
        "source_url": source_url,
    }


def _locate_product(raw: Any) -> dict[str, Any] | None:
    """Walk a potentially-nested JSON-LD/JSON blob and return the first
    node that looks like a Product passport."""
    queue: list[Any] = [raw]
    seen_ids = set()
    while queue:
        node = queue.pop(0)
        if isinstance(node, dict):
            ident = id(node)
            if ident in seen_ids:
                continue
            seen_ids.add(ident)
            t = node.get("@type") or node.get("type")
            if isinstance(t, list):
                t = " ".join(str(x) for x in t)
            t_lc = (t or "").lower() if isinstance(t, str) else ""
            # Heuristic: Product, GarmentProduct, ApparelProduct, DigitalProductPassport, etc.
            if any(k in t_lc for k in ("product", "garment", "apparel", "passport")):
                return node
            # Otherwise descend into all values.
            for v in node.values():
                if isinstance(v, (dict, list)):
                    queue.append(v)
            # JSON-LD @graph
            g = node.get("@graph")
            if isinstance(g, list):
                queue.extend(g)
        elif isinstance(node, list):
            queue.extend(node)
    # Fallback: if the root is a plain dict with any of the obvious
    # DPP fields, treat it as the product itself.
    if isinstance(raw, dict) and any(
        k in raw for k in (*_NAME_KEYS, *_MATERIAL_KEYS, *_BRAND_KEYS)
    ):
        return raw
    return None


def _first_string(node: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = node.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, list):
            for item in v:
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return None


def _first_scalar(node: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        v = node.get(k)
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            inner = v.get("value") or v.get("amount") or v.get("@value")
            if inner is not None:
                return inner
    return None


def _first_string_from_object(
    node: dict[str, Any], keys: tuple[str, ...]
) -> str | None:
    """Fetch a `.name` / `.label` / direct-string value from a nested object."""
    for k in keys:
        v = node.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for nk in ("name", "label", "@value", "value"):
                nv = v.get(nk)
                if isinstance(nv, str) and nv.strip():
                    return nv.strip()
        if isinstance(v, list) and v:
            first = v[0]
            if isinstance(first, str) and first.strip():
                return first.strip()
            if isinstance(first, dict):
                for nk in ("name", "label"):
                    nv = first.get(nk)
                    if isinstance(nv, str) and nv.strip():
                        return nv.strip()
    return None


def _first_image_url(node: dict[str, Any]) -> str | None:
    for k in _IMAGE_KEYS:
        v = node.get(k)
        if isinstance(v, str) and v.strip().startswith("http"):
            return v.strip()
        if isinstance(v, list):
            for item in v:
                if isinstance(item, str) and item.startswith("http"):
                    return item
                if isinstance(item, dict):
                    url = item.get("url") or item.get("contentUrl")
                    if isinstance(url, str) and url.startswith("http"):
                        return url
        if isinstance(v, dict):
            url = v.get("url") or v.get("contentUrl")
            if isinstance(url, str) and url.startswith("http"):
                return url
    return None


def _coerce_str_list(node: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for k in keys:
        v = node.get(k)
        if isinstance(v, str):
            for piece in v.split("\n"):
                s = piece.strip()
                if s and s.lower() not in seen:
                    out.append(s)
                    seen.add(s.lower())
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str) and item.strip():
                    s = item.strip()
                    if s.lower() not in seen:
                        out.append(s)
                        seen.add(s.lower())
                elif isinstance(item, dict):
                    s = item.get("name") or item.get("label") or item.get("value")
                    if isinstance(s, str) and s.strip() and s.lower() not in seen:
                        out.append(s.strip())
                        seen.add(s.lower())
    return out


def _normalise_colors(
    primary: str | None, colors_list: Any
) -> list[dict[str, Any]]:
    """Return list of `{name, pct}` dicts matching the WeightedTag shape
    used by GarmentAnalysis.colors."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    if primary:
        tag = primary.strip().lower()
        out.append({"name": tag, "pct": 100})
        seen.add(tag)
    if isinstance(colors_list, list):
        remaining = max(0, len(colors_list))
        for item in colors_list:
            tag: str | None = None
            pct: int | None = None
            if isinstance(item, str):
                tag = item.strip().lower()
            elif isinstance(item, dict):
                t = item.get("name") or item.get("tag") or item.get("label")
                if isinstance(t, str):
                    tag = t.strip().lower()
                w = item.get("weight") or item.get("percentage") or item.get("ratio") or item.get("pct")
                if isinstance(w, (int, float)):
                    frac = float(w) / (100.0 if w > 1 else 1.0)
                    pct = max(0, min(100, int(round(frac * 100))))
            if tag and tag not in seen:
                if pct is None and remaining:
                    pct = max(1, int(round(100.0 / remaining)))
                out.append({"name": tag, "pct": pct})
                seen.add(tag)
    return out[:6]


def _normalise_materials(product: dict[str, Any]) -> list[dict[str, Any]]:
    """Return `[{name, pct}]` — pct is integer 0..100, name is lower-case."""
    candidates: list[dict[str, Any]] = []
    for key in _MATERIAL_KEYS:
        v = product.get(key)
        if isinstance(v, str) and v.strip():
            # Try to parse strings like "80% cotton, 20% elastane"
            candidates.extend(_parse_material_string(v))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    candidates.extend(_parse_material_string(item))
                elif isinstance(item, dict):
                    tag = (
                        item.get("name")
                        or item.get("material")
                        or item.get("fiber")
                        or item.get("tag")
                    )
                    if not isinstance(tag, str) or not tag.strip():
                        continue
                    w = (
                        item.get("percentage")
                        or item.get("percent")
                        or item.get("weight")
                        or item.get("ratio")
                        or item.get("pct")
                    )
                    pct: int | None = None
                    if isinstance(w, (int, float)):
                        frac = float(w) / (100.0 if w > 1 else 1.0)
                        pct = max(0, min(100, int(round(frac * 100))))
                    candidates.append({"name": tag.strip().lower(), "pct": pct})

    # Drop dupes (prefer first) and fill missing percentages proportionally.
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for c in candidates:
        tag = c["name"]
        if tag in seen:
            continue
        seen.add(tag)
        uniq.append(c)
    if not uniq:
        return []
    known_pct = sum(c["pct"] for c in uniq if c.get("pct") is not None)
    missing = [c for c in uniq if c.get("pct") is None]
    if missing and known_pct < 100:
        share = max(1, int(round((100 - known_pct) / len(missing))))
        for c in missing:
            c["pct"] = share
    for c in uniq:
        if c.get("pct") is None:
            c["pct"] = 0
        c["pct"] = max(0, min(100, int(c["pct"])))
    return uniq[:6]


def _parse_material_string(text: str) -> list[dict[str, Any]]:
    """Parse strings like '80% cotton, 20% elastane' or 'cotton, polyester'."""
    out: list[dict[str, Any]] = []
    for chunk in text.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        pct: int | None = None
        remainder = chunk
        import re

        m = re.match(r"(\d{1,3})\s*%\s*(.+)$", chunk)
        if m:
            try:
                pct = max(0, min(100, int(m.group(1))))
            except ValueError:
                pct = None
            remainder = m.group(2).strip()
        if remainder:
            out.append({"name": remainder.lower(), "pct": pct})
    return out


def _extract_jsonld_from_html(body: bytes) -> Any:
    """Find the first `<script type="application/ld+json">` payload."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(body, "html.parser")
        nodes = soup.find_all("script", attrs={"type": "application/ld+json"})
        for node in nodes:
            text = node.string or node.get_text() or ""
            text = text.strip()
            if not text:
                continue
            try:
                return json.loads(text)
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        logger.info("dpp: html jsonld extract failed: %s", exc)
    return None


# ---------------------------------------------------------------------
# SSRF guard
# ---------------------------------------------------------------------
def _is_public_url(url: str) -> bool:
    """Block loopback / link-local / private-network IPs."""
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    # Reject obvious metadata/localhost-like hostnames outright.
    lowered = host.lower()
    if lowered in {"localhost", "metadata", "metadata.google.internal"}:
        return False
    try:
        # If it's already an IP, check it directly; otherwise resolve.
        try:
            ip = ipaddress.ip_address(host)
            ips = [ip]
        except ValueError:
            infos = socket.getaddrinfo(host, None)
            ips = [ipaddress.ip_address(info[4][0]) for info in infos]
    except Exception as exc:  # noqa: BLE001
        logger.info("dpp: DNS resolve failed for %s: %s", host, exc)
        return False
    for ip in ips:
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True
