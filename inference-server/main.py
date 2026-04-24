"""DressApp self-hosted inference server (Phase V).

FastAPI microservice packaging the two commercial-safe vision models
used by the DressApp closet pipeline:

  - POST /segment-clothes      sayeed99/segformer_b3_clothes (MIT)
  - POST /remove-background    ZhengPeng7/BiRefNet           (MIT)

Design: load models once at startup, keep them resident on GPU (or CPU
in a pinch), accept multipart/form-data image uploads, return JSON that
our FastAPI backend already knows how to consume.

Deploy anywhere with an NVIDIA GPU (Modal / RunPod / Lambda Labs / your
own rented VM). See README.md for the exact commands.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
import torch
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from PIL import Image
from torchvision import transforms
from transformers import AutoModelForSemanticSegmentation, SegformerImageProcessor

log = logging.getLogger("inference")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

API_TOKEN = os.environ.get("INFERENCE_API_TOKEN")  # set in prod
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
CLOTHES_MODEL = os.environ.get("CLOTHES_MODEL", "sayeed99/segformer_b3_clothes")
MATTING_MODEL = os.environ.get("MATTING_MODEL", "ZhengPeng7/BiRefNet")

_STATE: dict[str, Any] = {}


def _require_token(authorization: str | None = Header(default=None)) -> None:
    if not API_TOKEN:
        return  # disabled in dev
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    if authorization.split(" ", 1)[1].strip() != API_TOKEN:
        raise HTTPException(401, "Bad bearer token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Loading clothes parser: %s on %s", CLOTHES_MODEL, DEVICE)
    _STATE["clothes_proc"] = SegformerImageProcessor.from_pretrained(CLOTHES_MODEL)
    _STATE["clothes_model"] = (
        AutoModelForSemanticSegmentation.from_pretrained(CLOTHES_MODEL)
        .to(DEVICE)
        .eval()
    )

    log.info("Loading matting model: %s on %s", MATTING_MODEL, DEVICE)
    matting = AutoModelForSemanticSegmentation.from_pretrained(
        MATTING_MODEL, trust_remote_code=True
    )
    matting.to(DEVICE).eval()
    if hasattr(torch, "set_float32_matmul_precision"):
        torch.set_float32_matmul_precision("high")
    _STATE["matting_model"] = matting
    _STATE["matting_tfm"] = transforms.Compose(
        [
            transforms.Resize((1024, 1024)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )
    log.info("Models loaded.")
    yield
    _STATE.clear()


app = FastAPI(title="DressApp Inference", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {
        "ok": True,
        "device": DEVICE,
        "clothes_model": CLOTHES_MODEL,
        "matting_model": MATTING_MODEL,
    }


# -------------------- /segment-clothes --------------------
def _b64_png(mask: np.ndarray) -> str:
    im = Image.fromarray((mask * 255).astype(np.uint8), mode="L")
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


@app.post("/segment-clothes", dependencies=[Depends(_require_token)])
async def segment_clothes(image: UploadFile = File(...)) -> dict[str, Any]:
    data = await image.read()
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Invalid image: {exc}") from exc
    proc: SegformerImageProcessor = _STATE["clothes_proc"]
    model = _STATE["clothes_model"]
    started = time.time()
    with torch.no_grad():
        inputs = proc(images=img, return_tensors="pt").to(DEVICE)
        outputs = model(**inputs)
        logits = outputs.logits  # (1, C, h, w)
        up = torch.nn.functional.interpolate(
            logits, size=img.size[::-1], mode="bilinear", align_corners=False
        )
        pred = up.argmax(dim=1)[0].cpu().numpy()
    id2label = model.config.id2label
    segments = []
    for cls_id, label in id2label.items():
        mask = (pred == cls_id).astype(np.uint8)
        if mask.sum() == 0:
            continue
        segments.append(
            {
                "label": label,
                "score": 1.0,  # argmax — no per-pixel prob exposed
                "mask": f"data:image/png;base64,{_b64_png(mask)}",
            }
        )
    log.info(
        "segment-clothes: %d segments in %.1fms",
        len(segments),
        (time.time() - started) * 1000,
    )
    return {"segments": segments}


# -------------------- /remove-background --------------------
@app.post("/remove-background", dependencies=[Depends(_require_token)])
async def remove_background(image: UploadFile = File(...)) -> dict[str, Any]:
    data = await image.read()
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Invalid image: {exc}") from exc
    model = _STATE["matting_model"]
    tfm = _STATE["matting_tfm"]
    started = time.time()
    with torch.no_grad():
        x = tfm(img).unsqueeze(0).to(DEVICE)
        preds = model(x)[-1].sigmoid().cpu()
    pred = preds[0].squeeze()
    mask = Image.fromarray((pred.numpy() * 255).astype(np.uint8), mode="L").resize(img.size)
    rgba = img.convert("RGBA")
    rgba.putalpha(mask)
    out = io.BytesIO()
    rgba.save(out, format="PNG", optimize=True)
    log.info("remove-background in %.1fms", (time.time() - started) * 1000)
    return {"image_png_b64": base64.b64encode(out.getvalue()).decode("ascii")}
