/**
 * Pick the most appropriate user size preference for a given garment
 * category.
 *
 * Used by Add Item (when analysing a fresh upload) and Item Detail
 * (when re-analysing or first opening an item with no size set) to
 * pre-fill the size field with the user's known measurement, instead
 * of leaving it empty when the analyser couldn't read a label.
 *
 * Returns ``''`` when the user hasn't entered a relevant preference
 * — callers should treat that as "no default" and leave the field
 * empty.
 *
 * @param {object|null|undefined} user — the auth user object (must
 *   contain ``body_measurements`` and ``sex`` to be useful).
 * @param {object} item — partial garment shape; we read ``category``,
 *   ``sub_category`` and ``item_type`` to pick the right slot.
 * @returns {string} the user's preferred size, or ``''``.
 */
export function deriveSizeFromPreferences(user, item) {
  if (!user || !user.body_measurements) return '';
  const meas = user.body_measurements || {};
  const cat = String(item?.category || '').toLowerCase();
  const sub = String(item?.sub_category || '').toLowerCase();
  const type = String(item?.item_type || '').toLowerCase();
  const blob = `${sub} ${type}`;

  const pick = (...keys) => {
    for (const k of keys) {
      const v = meas[k];
      if (v != null && String(v).trim() !== '') return String(v).trim();
    }
    return '';
  };

  // Footwear → shoe size always wins, regardless of sub_category.
  if (cat === 'footwear' || /shoe|sneaker|boot|sandal|heel|loafer/.test(blob)) {
    return pick('shoe_size');
  }

  // Underwear: bra for females (and items obviously bra-shaped),
  // otherwise fall through to the generic torso/shirt size so we
  // don't accidentally suggest a bra size for boxer-briefs.
  if (cat === 'underwear' || /bra|bralette|lingerie/.test(blob)) {
    if (/bra|bralette/.test(blob) || user?.sex === 'female') {
      return pick('bra_size', 'shirt_size');
    }
    return pick('shirt_size');
  }

  // Full-body / dress-coded garments → dress_size first, fallback
  // to shirt_size so we still surface SOMETHING for jumpsuits etc.
  if (cat === 'full body' || /dress|jumpsuit|gown|kaftan|robe/.test(blob)) {
    return pick('dress_size', 'shirt_size');
  }

  // Skirts: sized off the waist most commonly — dress_size is the
  // closest proxy when the user only filled in dress sizing; shirt
  // size is the last resort.
  if (/skirt/.test(blob)) {
    return pick('dress_size', 'pants_size', 'shirt_size');
  }

  // Bottoms (pants, jeans, shorts, …)
  if (cat === 'bottom' || /pants|jeans|trouser|short|legging/.test(blob)) {
    return pick('pants_size');
  }

  // Default: top / outerwear / accessories — shirt size is the
  // best general proxy. Accessories with no plausible sizing get
  // an empty string and the form stays blank.
  if (
    cat === 'top' ||
    cat === 'outerwear' ||
    /shirt|tee|t-shirt|blouse|sweater|hoodie|jacket|coat|cardigan|blazer/.test(
      blob,
    )
  ) {
    return pick('shirt_size');
  }

  return '';
}
