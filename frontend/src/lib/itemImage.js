/**
 * Centralised "best image" resolver for a ClosetItem document.
 *
 * Five image fields can exist on a single item, in priority order:
 *
 *   1. ``thumbnail_data_url``    \u2014 user-uploaded explicit thumbnail (Phase Q).
 *   2. ``reconstructed_image_url`` \u2014 Nano-Banana studio reshoot (user-initiated).
 *   3. ``clean_image_url``       \u2014 Phase O.6 background-rembg PNG cutout.
 *   4. ``segmented_image_url``   \u2014 legacy synchronous SegFormer JPG.
 *   5. ``original_image_url``    \u2014 the raw upload.
 *
 * Every closet thumbnail, listing card, swap picker, stylist outfit card and
 * marketplace cover used to inline this chain in slightly different orders,
 * which made it impossible to land a new field (like ``clean_image_url``)
 * without sweeping ~6 files. This helper centralises the policy so the
 * chain is one edit away from changing in lock-step everywhere.
 *
 * ``opts.skipReconstruction``  \u2014 set to ``true`` on screens that want to
 * show the original ("flat", non-reshoot) version, e.g. the "Show original"
 * toggle on ItemDetail. Bypasses fields #1-#2 only.
 */
export function bestImageUrl(item, opts = {}) {
  if (!item) return null;
  if (!opts.skipReconstruction) {
    if (item.thumbnail_data_url) return item.thumbnail_data_url;
    if (item.reconstructed_image_url) return item.reconstructed_image_url;
  }
  if (item.clean_image_url) return item.clean_image_url;
  if (item.segmented_image_url) return item.segmented_image_url;
  if (item.original_image_url) return item.original_image_url;
  return null;
}

/**
 * Returns ``true`` when the backend is still running its
 * fire-and-forget rembg matte for a Phase-O.6 single-pass item.
 *
 * The closet card uses this to overlay a subtle "polishing photo\u2026"
 * shimmer on the thumbnail until the alpha PNG arrives \u2014 typically
 * 4-8 s after ``POST /closet`` returns.
 */
export function isCleanImagePending(item) {
  return !!(item && item.clean_image_status === 'pending');
}
