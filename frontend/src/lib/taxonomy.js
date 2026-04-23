/**
 * Taxonomy label helpers.
 *
 * The backend stores stable English codes for category / dress_code / gender /
 * season / state / condition / quality / pattern / formality / intent / source,
 * and `role` for stylist recommendation items. This module converts those
 * codes into display labels honoring the active i18next locale, with a safe
 * fallback that keeps the original code if we don't have a translation yet.
 *
 * Usage:
 *   const { t } = useTranslation();
 *   <SelectItem value="top">{labelForCategory('top', t)}</SelectItem>
 */

/**
 * Normalize a taxonomy code into the key shape we use in locale files.
 *
 * Category labels in the DB/API often arrive capitalized (e.g. "Top",
 * "Full Body", "Accessories"). We map them to lowercase with underscore
 * separators so JSON keys stay predictable.
 */
const slug = (value) =>
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '_');

const fallback = (t, key, raw) => {
  const out = t(key, { defaultValue: raw ?? '' });
  // i18next will return the key itself when nothing matches — degrade to raw.
  if (!out || out === key) return raw ?? '';
  return out;
};

export const labelForCategory = (code, t) => {
  if (!code) return '';
  if (code === 'all') return fallback(t, 'taxonomy.categories.all', 'All');
  const key = `taxonomy.categories.${slug(code)}`;
  return fallback(t, key, code);
};

export const labelForDressCode = (code, t) => {
  if (!code) return '';
  // Keep the original code (e.g. "smart-casual") so JSON keys match.
  const key = `taxonomy.dress_code.${code}`;
  return fallback(t, key, code);
};

export const labelForGender = (code, t) => {
  if (!code) return '';
  const key = `taxonomy.gender.${code}`;
  return fallback(t, key, code);
};

export const labelForSeason = (code, t) => {
  if (!code) return '';
  const key = `taxonomy.season.${code}`;
  return fallback(t, key, code);
};

export const labelForState = (code, t) => {
  if (!code) return '';
  const key = `taxonomy.state.${code}`;
  return fallback(t, key, code);
};

export const labelForCondition = (code, t) => {
  if (!code) return '';
  const key = `taxonomy.condition.${code}`;
  return fallback(t, key, code);
};

export const labelForQuality = (code, t) => {
  if (!code) return '';
  const key = `taxonomy.quality.${code}`;
  return fallback(t, key, code);
};

export const labelForPattern = (code, t) => {
  if (!code) return '';
  const key = `taxonomy.pattern.${code}`;
  return fallback(t, key, code);
};

export const labelForFormality = (code, t) => {
  if (!code) return '';
  const key = `taxonomy.formality.${code}`;
  return fallback(t, key, code);
};

export const labelForIntent = (code, t) => {
  if (!code) return '';
  const key = `taxonomy.intent.${code}`;
  return fallback(t, key, code);
};

export const labelForSource = (code, t) => {
  if (!code) return '';
  if (code === 'all') return fallback(t, 'taxonomy.source.all', 'All sources');
  // Source codes in the DB are capitalized: Private | Shared | Retail.
  const key = `taxonomy.source.${code}`;
  return fallback(t, key, code);
};

export const labelForRole = (code, t) => {
  if (!code) return '';
  const key = `taxonomy.role.${code}`;
  return fallback(t, key, code);
};

/**
 * Sub-category / item-type labels.
 *
 * Backend stores these as free-form English text (e.g., "Pants", "Shorts",
 * "Oxford shirt"). We normalize to a slug and look up a localized label; if
 * we don't have a translation we return the raw value unchanged so non-
 * dictionary garments (e.g., brand-specific nomenclature) still render.
 */
const itemSlug = (value) =>
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/['’`]/g, '')
    .replace(/[\s\/\-]+/g, '_')
    .replace(/[^a-z0-9_]/g, '');

export const labelForSubCategory = (raw, t) => {
  if (!raw) return '';
  const slug = itemSlug(raw);
  if (!slug) return raw;
  const key = `taxonomy.sub_category.${slug}`;
  return fallback(t, key, raw);
};

export const labelForItemType = (raw, t) => {
  if (!raw) return '';
  const slug = itemSlug(raw);
  if (!slug) return raw;
  const key = `taxonomy.item_type.${slug}`;
  return fallback(t, key, raw);
};

/** Generic helper to map an array of codes into translated Select-ready objects. */
export const makeLabeledOptions = (codes, labelFn, t) =>
  (codes || []).map((code) => ({ value: code, label: labelFn(code, t) }));
