import { clsx } from "clsx";
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

/**
 * Phase Z2 — compute the SHA-256 of a File / Blob entirely in-browser.
 *
 * Used by the pre-flight duplicate check before /closet/preflight.
 * `crypto.subtle.digest('SHA-256', …)` is built into every modern
 * browser (Chrome 38+, Safari 11+, Firefox 34+) and runs off the main
 * thread, so even a 10 MB JPEG is ~50 ms on a phone.
 *
 * @param {File|Blob} file
 * @returns {Promise<string>} 64-char lowercase hex digest
 */
export async function sha256File(file) {
  if (!file || typeof file.arrayBuffer !== "function") return null;
  try {
    const buf = await file.arrayBuffer();
    const digest = await crypto.subtle.digest("SHA-256", buf);
    const bytes = new Uint8Array(digest);
    let out = "";
    for (let i = 0; i < bytes.length; i++) {
      out += bytes[i].toString(16).padStart(2, "0");
    }
    return out;
  } catch (_) {
    // Old browser or memory pressure on a huge file — degrade gracefully:
    // the upload still proceeds, the duplicate check just gets skipped
    // for this one file. The backend never sees a sha256 → no false hits.
    return null;
  }
}

/**
 * Phase Z2.1 — compute a 64-bit average-hash (aHash) of an image File.
 *
 * Mirrors the backend's `image_hash.average_hash` exactly:
 *   1. decode the file into an HTMLImageElement
 *   2. draw it onto a hidden 8x8 grayscale canvas
 *   3. for each pixel, output 1 if luminance > average else 0
 *   4. pack 64 bits → 8 bytes → 16-char lowercase hex
 *
 * Survives JPEG re-compression, mild crops, and small lighting
 * shifts — meaning the pre-flight catches duplicates of legacy
 * closet items whose `source_sha256` was never captured (the original
 * bytes weren't preserved at upload time, only the thumbnail).
 *
 * @param {File|Blob} file
 * @returns {Promise<string|null>} 16-char lowercase hex digest
 */
export async function aHashFile(file) {
  if (!file) return null;
  try {
    // Use ImageBitmap when available — faster, off-main-thread,
    // doesn't trigger paint. Fall back to <img> for older Safari.
    let bmp = null;
    if (typeof createImageBitmap === "function") {
      try {
        bmp = await createImageBitmap(file);
      } catch (_) {
        bmp = null;
      }
    }
    if (!bmp) {
      const dataUrl = await new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result);
        r.onerror = reject;
        r.readAsDataURL(file);
      });
      bmp = await new Promise((resolve, reject) => {
        const im = new Image();
        im.onload = () => resolve(im);
        im.onerror = reject;
        im.src = dataUrl;
      });
    }
    const HASH_SIZE = 8;
    const canvas = document.createElement("canvas");
    canvas.width = HASH_SIZE;
    canvas.height = HASH_SIZE;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return null;
    // Filter == grayscale → match backend's `.convert('L')` step.
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(bmp, 0, 0, HASH_SIZE, HASH_SIZE);
    const { data } = ctx.getImageData(0, 0, HASH_SIZE, HASH_SIZE);
    // Luminance per ITU-R BT.601 (matches PIL .convert('L')).
    const lum = new Uint8Array(HASH_SIZE * HASH_SIZE);
    let sum = 0;
    for (let i = 0, j = 0; i < data.length; i += 4, j += 1) {
      const v = Math.round(
        0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2],
      );
      lum[j] = v;
      sum += v;
    }
    const avg = sum / lum.length;
    // Pack 64 bits big-endian, just like Python's np.packbits default.
    const bytes = new Uint8Array(8);
    for (let i = 0; i < 64; i++) {
      const bit = lum[i] > avg ? 1 : 0;
      bytes[i >> 3] |= bit << (7 - (i & 7));
    }
    let out = "";
    for (let i = 0; i < bytes.length; i++) {
      out += bytes[i].toString(16).padStart(2, "0");
    }
    return out;
  } catch (_) {
    return null;
  }
}

/**
 * Phase Z2.2 — compute a 24-byte RGB colour signature (4 quadrants ×
 * 3 channels). Mirrors the backend's `image_hash.color_signature`.
 *
 * Why we need it: the aHash above throws away colour by converting
 * to luminance — that's intentional for matching the *same garment*
 * across lighting changes, but it's why a navy and a grey pair of
 * shorts of the same cut produced near-identical hashes. The colour
 * signature recovers enough chroma information to tell those apart
 * without sacrificing the aHash's robustness to lighting.
 *
 * Output is 48 hex chars (24 bytes). Backend computes Manhattan
 * distance and rejects matches over `DEFAULT_COLOR_THRESHOLD`.
 *
 * @param {File|Blob} file
 * @returns {Promise<string|null>} 48-char lowercase hex digest
 */
export async function colorSignatureFile(file) {
  if (!file) return null;
  try {
    let bmp = null;
    if (typeof createImageBitmap === "function") {
      try { bmp = await createImageBitmap(file); } catch (_) { bmp = null; }
    }
    if (!bmp) {
      const dataUrl = await new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result);
        r.onerror = reject;
        r.readAsDataURL(file);
      });
      bmp = await new Promise((resolve, reject) => {
        const im = new Image();
        im.onload = () => resolve(im);
        im.onerror = reject;
        im.src = dataUrl;
      });
    }
    // Resize to 16x16 — large enough to be representative, small
    // enough that the readback is sub-millisecond on mobile.
    const SIZE = 16;
    const GRID = 2; // 2x2 grid of quadrants → 4 quadrants × 3 channels
    const canvas = document.createElement("canvas");
    canvas.width = SIZE;
    canvas.height = SIZE;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return null;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(bmp, 0, 0, SIZE, SIZE);
    const { data } = ctx.getImageData(0, 0, SIZE, SIZE);
    const cell = SIZE / GRID; // 8
    const out = new Uint8Array(GRID * GRID * 3);
    let outIdx = 0;
    for (let gy = 0; gy < GRID; gy++) {
      for (let gx = 0; gx < GRID; gx++) {
        let r = 0, g = 0, b = 0, n = 0;
        for (let yy = 0; yy < cell; yy++) {
          for (let xx = 0; xx < cell; xx++) {
            const px = ((gy * cell + yy) * SIZE + (gx * cell + xx)) * 4;
            r += data[px];
            g += data[px + 1];
            b += data[px + 2];
            n += 1;
          }
        }
        out[outIdx++] = Math.round(r / n);
        out[outIdx++] = Math.round(g / n);
        out[outIdx++] = Math.round(b / n);
      }
    }
    let hex = "";
    for (let i = 0; i < out.length; i++) hex += out[i].toString(16).padStart(2, "0");
    return hex;
  } catch (_) {
    return null;
  }
}
