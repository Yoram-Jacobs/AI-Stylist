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
