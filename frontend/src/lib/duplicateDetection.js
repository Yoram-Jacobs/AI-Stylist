/**
 * duplicateDetection.js — client-side duplicate detection for the
 * Add-Item upload flow.
 *
 * Phase Z3 — DressApp's pre-flight duplicate check used to round-trip
 * to the backend (``POST /closet/preflight``), even though by the time
 * the user opens Add-Item the entire closet is already cached in
 * ``closetStore`` — including every item's ``source_sha256``,
 * ``source_phash`` and ``source_color_sig``. That round-trip cost
 * 300–1500 ms per upload batch (network + Mongo scan + opportunistic
 * lazy backfill) for information the client already possesses. This
 * module reproduces the backend's matching logic locally so the
 * pre-flight check is a fast, offline operation against the closet
 * snapshot.
 *
 * The matching logic is a 1:1 port of ``image_hash.is_duplicate_match``
 * (Python side, ``backend/app/services/image_hash.py``). Both sides
 * MUST keep their thresholds and decision tree in sync — otherwise an
 * item that passes pre-flight on the client could still be flagged on
 * save, leading to confusing UX. Any change here needs the same
 * change there.
 *
 * Returns the same payload shape that ``POST /closet/preflight`` used
 * to return, so the ``DuplicatePreflightDialog`` stays untouched:
 *
 *     { matches: [
 *         { sha256, phash, filename, size_bytes,
 *           existing: { id, title, item_type, sub_category, color,
 *                       thumbnail_data_url, is_duplicate }},
 *         ...
 *     ]}
 *
 * Trade-off accepted (Q1a in the design discussion): pre-Z2 legacy
 * items that lack ``source_phash`` simply don't participate in
 * detection — they get a "free pass" through the pre-flight gate.
 * The backend's post-save duplicate guard still catches obvious
 * re-uploads of new items.
 */

// Match the backend constants exactly. If you change these, change
// ``DEFAULT_HAMMING_THRESHOLD`` / ``DEFAULT_COLOR_THRESHOLD`` in
// ``image_hash.py`` to the same values.
const HAMMING_THRESHOLD = 6;
const COLOR_THRESHOLD = 220;

// Sentinel values mirror the Python helper — these effectively mean
// "treat as no-match" so callers don't have to special-case nulls.
const HAMMING_SENTINEL = 65;
const COLOR_SENTINEL = 10_000;

/**
 * Hamming distance between two 16-char hex aHash digests. Returns a
 * sentinel (65, above any real distance) for malformed inputs.
 */
export function hammingDistance(a, b) {
  if (!a || !b || a.length !== b.length) return HAMMING_SENTINEL;
  try {
    // 64-bit hash; JS numbers can't safely hold a 64-bit int, so XOR
    // byte-by-byte and popcount each byte. This stays in the
    // 32-bit-safe regime and is a few microseconds for 16 hex chars.
    let dist = 0;
    for (let i = 0; i < a.length; i += 2) {
      const ai = parseInt(a.slice(i, i + 2), 16);
      const bi = parseInt(b.slice(i, i + 2), 16);
      if (Number.isNaN(ai) || Number.isNaN(bi)) return HAMMING_SENTINEL;
      let x = ai ^ bi;
      // Brian Kernighan popcount on an 8-bit value.
      while (x) { dist += 1; x &= x - 1; }
    }
    return dist;
  } catch {
    return HAMMING_SENTINEL;
  }
}

/**
 * Manhattan distance between two 24-char hex colour signatures
 * (4 quadrants × 3 RGB channels = 12 bytes). Range 0..3060.
 */
export function colorDistance(a, b) {
  if (!a || !b || a.length !== b.length) return COLOR_SENTINEL;
  try {
    let dist = 0;
    for (let i = 0; i < a.length; i += 2) {
      const ai = parseInt(a.slice(i, i + 2), 16);
      const bi = parseInt(b.slice(i, i + 2), 16);
      if (Number.isNaN(ai) || Number.isNaN(bi)) return COLOR_SENTINEL;
      dist += Math.abs(ai - bi);
    }
    return dist;
  } catch {
    return COLOR_SENTINEL;
  }
}

/**
 * Single source of truth for "are these two images duplicates?". 1:1
 * port of the backend's ``is_duplicate_match``. Decision tree:
 *
 *   1. Exact SHA-256 match → duplicate (re-upload of the same bytes).
 *   2. Shape similar (Hamming ≤ 6) AND
 *      (no colour sig on either side OR colour distance ≤ 220)
 *      → duplicate.
 *   3. Otherwise → not a duplicate.
 *
 * Colour gate prevents "navy shorts flagged as a duplicate of grey
 * shorts of the same cut" — the bug that originally motivated adding
 * the colour sig to the schema.
 */
export function isDuplicateMatch({
  shaA, shaB, phashA, phashB, colorA, colorB,
  hammingThreshold = HAMMING_THRESHOLD,
  colorThreshold = COLOR_THRESHOLD,
} = {}) {
  // Pass 1 — exact byte match.
  if (shaA && shaB && shaA === shaB) return true;
  // Pass 2 — shape similarity is the prerequisite; without phashes
  // we can't say anything about visual similarity.
  if (!phashA || !phashB) return false;
  if (hammingDistance(phashA, phashB) > hammingThreshold) return false;
  // Shape says "match"; gate on colour if we have it on both sides.
  if (colorA && colorB) {
    return colorDistance(colorA, colorB) <= colorThreshold;
  }
  // Phash-only fallback for closet items that pre-date the
  // colour-sig backfill (mostly pre-Phase-Z2 items).
  return true;
}

/**
 * Find pre-flight duplicate matches for an incoming upload batch by
 * scanning the locally-cached closet snapshot. No network round-trip.
 *
 * @param {Array<{
 *   sha256?: string|null,
 *   phash?: string|null,
 *   color_sig?: string|null,
 *   filename?: string|null,
 *   size_bytes?: number|null,
 * }>} fingerprints       — one entry per file the user is uploading
 * @param {Array<object>}  closetItems — the ``items`` array from
 *                          ``closetStore``. Items WITHOUT a
 *                          ``source_phash`` are silently skipped
 *                          (Q1a — accepted trade-off).
 * @returns {{ matches: Array<object> }} same shape the backend
 *          ``/closet/preflight`` used to return; consumed verbatim by
 *          ``DuplicatePreflightDialog``.
 */
export function findDuplicatesInCloset(fingerprints, closetItems) {
  if (!Array.isArray(fingerprints) || fingerprints.length === 0) {
    return { matches: [] };
  }
  if (!Array.isArray(closetItems) || closetItems.length === 0) {
    return { matches: [] };
  }

  // Filter to candidates with at least one usable hash. Saves the
  // tight inner-loop from re-checking blank items every iteration.
  const candidates = closetItems.filter(
    (it) => it && (it.source_sha256 || it.source_phash),
  );
  if (candidates.length === 0) return { matches: [] };

  // Pre-index by sha256 for the O(1) exact-byte pass — most matches
  // in practice come from this path (genuine re-uploads).
  const byShaSha = new Map();
  for (const it of candidates) {
    if (it.source_sha256) byShaSha.set(it.source_sha256, it);
  }

  const matches = [];
  const seen = new Set();
  for (const p of fingerprints) {
    if (!p) continue;
    let existing = null;

    // Pass 1 — exact byte match.
    if (p.sha256 && byShaSha.has(p.sha256)) {
      existing = byShaSha.get(p.sha256);
    }

    // Pass 2 — shape + colour. Pick the best (lowest-Hamming) match
    // so the dialog shows the strongest visual neighbour, not just
    // the first acceptable one.
    if (!existing && p.phash) {
      let bestDist = HAMMING_THRESHOLD + 1;
      for (const it of candidates) {
        if (
          !isDuplicateMatch({
            shaA: p.sha256,
            shaB: it.source_sha256,
            phashA: p.phash,
            phashB: it.source_phash,
            colorA: p.color_sig,
            colorB: it.source_color_sig,
          })
        ) {
          continue;
        }
        const d = hammingDistance(p.phash, it.source_phash);
        if (d < bestDist) {
          bestDist = d;
          existing = it;
        }
      }
    }

    if (!existing) continue;

    // De-dupe a single incoming photo that hits both passes — e.g.
    // a bytewise-identical re-upload also has Hamming 0 against
    // itself. Same key the backend uses, so any downstream code that
    // grouped by `${sha}|${phash}` keeps working.
    const key = `${p.sha256 || ''}|${p.phash || ''}`;
    if (seen.has(key)) continue;
    seen.add(key);

    matches.push({
      sha256: p.sha256 || null,
      phash: p.phash || null,
      filename: p.filename || null,
      size_bytes: typeof p.size_bytes === 'number' ? p.size_bytes : null,
      existing: {
        id: existing.id,
        title: existing.title || existing.name || 'Existing item',
        item_type: existing.item_type || null,
        sub_category: existing.sub_category || null,
        color: existing.color || null,
        // Prefer the cheap thumbnail; fall back through the heavier
        // URLs so the dialog always has something to render. Mirrors
        // the backend's exact precedence.
        thumbnail_data_url:
          existing.thumbnail_data_url
          || existing.segmented_image_url
          || existing.original_image_url
          || null,
        is_duplicate: !!existing.is_duplicate,
      },
    });
  }

  return { matches };
}

export const __testables = {
  HAMMING_THRESHOLD,
  COLOR_THRESHOLD,
  HAMMING_SENTINEL,
  COLOR_SENTINEL,
};
