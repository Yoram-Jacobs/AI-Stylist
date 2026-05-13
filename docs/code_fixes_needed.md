# Code Fixes Needed — Already-Translated Strings Not Yet Wired Up

This file documents UI strings that **already have correct translations in every
locale JSON** but still render in English because the React code dumps a raw
backend value or uses a non-existent i18n key with an English `defaultValue`.

These are **code patches**, not translation tasks. Each fix is small (1–5
lines) and unlocks ~50 visible strings on non-English UIs.

---

## 1. Listing chips dump raw enum values instead of `t(...)` — `src/pages/ListingDetail.jsx`

### 1a. `{listing.category}` renders the raw backend category

**Symptom (zh UI):** chip shows `Accessories` instead of `配饰`.

**Lines:** `src/pages/ListingDetail.jsx:169-170`

```jsx
// Before — raw enum bleed
{listing.category && (
  <Badge variant="secondary">{listing.category}</Badge>
)}

// After — route through the taxonomy.categories.* map (already in every locale)
{listing.category && (
  <Badge variant="secondary">
    {t(`taxonomy.categories.${listing.category}`, { defaultValue: listing.category })}
  </Badge>
)}
```

### 1b. `{listing.mode}` renders raw `sell` / `donate` / `swap`

**Symptom (zh UI):** chip shows `Donate` instead of `捐赠`.

**Lines:** `src/pages/ListingDetail.jsx:172-180`

```jsx
// Before
{listing.mode && listing.mode !== 'sell' && (
  <Badge className="capitalize" variant="outline" data-testid="listing-detail-mode">
    {listing.mode}
  </Badge>
)}

// After — taxonomy.intent.* already exists in every locale
{listing.mode && listing.mode !== 'sell' && (
  <Badge variant="outline" data-testid="listing-detail-mode">
    {t(`taxonomy.intent.${listing.mode}`, { defaultValue: listing.mode })}
  </Badge>
)}
```

### 1c. `Condition: good` uses a non-existent key

**Symptom:** zh UI shows `Condition: good` instead of `状况：良好`. The
`defaultValue` is doing all the work because `market.conditionLabel` was
never added to any locale.

**Lines:** `src/pages/ListingDetail.jsx:160-166`

```jsx
// Before
{listing.condition && (
  <Badge variant="outline" data-testid="listing-detail-condition">
    {t('market.conditionLabel', { defaultValue: 'Condition' })}:{' '}
    {String(listing.condition).replace('_', ' ')}
  </Badge>
)}

// After — use the existing addItem.condition + taxonomy.condition.* keys
{listing.condition && (
  <Badge variant="outline" data-testid="listing-detail-condition">
    {t('addItem.condition')}:{' '}
    {t(`taxonomy.condition.${listing.condition}`, { defaultValue: listing.condition })}
  </Badge>
)}
```

### 1d. `Size: M` — same pattern as 1c

**Lines:** `src/pages/ListingDetail.jsx:155-159`

```jsx
// Before
{listing.size && (
  <Badge variant="outline" data-testid="listing-detail-size">
    {t('market.sizeLabel', { defaultValue: 'Size' })}: {listing.size}
  </Badge>
)}

// After
{listing.size && (
  <Badge variant="outline" data-testid="listing-detail-size">
    {t('addItem.size')}: {listing.size}
  </Badge>
)}
```

---

## 2. Trend cards show English bucket labels on non-English UIs — `src/pages/Home.jsx`

### 2a. Card `chip` falls back to `_prettyBucket()` which converts snake_case to English title-case

**Symptom (zh UI):** card header shows `News Flash` instead of `新闻速递`.

**Root cause:** `card.label` comes from the backend Trend-Scout API in English
only. The frontend has no i18n map for the known bucket enum.

**Step 1 — add a new translation block to every locale.** Add the following
keys (with translations) into each `/app/frontend/src/locales/<loc>.json`:

```jsonc
"trends": {
  "bucket": {
    "ss26_runway":    "SS26 Runway",
    "street":         "Street",
    "sustainability": "Sustainability",
    "influencers":    "Influencers",
    "second_hand":    "Second-hand",
    "recycling":      "Recycling",
    "news_flash":     "News Flash"
  }
}
```

(Translate each value in each locale file.)

**Step 2 — wire it in:**

**Lines:** `src/pages/Home.jsx:292-296`

```jsx
// Before
const _prettyBucket = (b) =>
  (b || '')
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
const chip = card.label || _prettyBucket(card.bucket) || card.tag;

// After — prefer the localised bucket label; the backend label is a hard fallback
const chip =
  (card.bucket && t(`trends.bucket.${card.bucket}`, { defaultValue: '' }))
  || card.label
  || card.tag;
```

### 2b. `FALLBACK_TRENDS` constant uses raw English strings

**Lines:** `src/pages/Home.jsx:35-39`

The fallback array is module-scope, so `t()` is not in scope. Either:

- **Option A (preferred):** move it inside the `Home()` component as a
  `useMemo` so `t` is available. Replace each `label`/`headline`/`summary`
  with `t('home.fallbackTrends.*')` lookups.
- **Option B:** keep the constant at module scope but store i18n keys
  instead of literals, and translate at render time:

```jsx
const FALLBACK_TRENDS = [
  { id: 'fb-1', _key: 'fb1' },
  { id: 'fb-2', _key: 'fb2' },
  { id: 'fb-3', _key: 'fb3' },
];
// then at render:
const card = { ...raw,
  label:    t(`home.fallbackTrends.${raw._key}.label`),
  headline: t(`home.fallbackTrends.${raw._key}.headline`),
  summary:  t(`home.fallbackTrends.${raw._key}.summary`),
};
```

The automated patcher in `/app/scripts/patch_hardcoded_strings.py` handles
in-component literals but **skips module-scope objects** like
`FALLBACK_TRENDS`. Those are listed in the patcher's skip log and need
manual treatment.

---

## 3. SEO meta strings live at module scope — `src/components/SeoBase.jsx`

`META` is a module-level dictionary mapping route paths to `{title, description}`
strings. These render into `<title>` and `<meta name="description">` tags via
react-helmet. Same module-scope problem as FALLBACK_TRENDS.

**Recommended pattern:**

```jsx
// Replace the META constant with i18n keys
const META = {
  '/':           { titleKey: 'seo.login.title',    descKey: 'seo.login.description' },
  '/closet':     { titleKey: 'seo.closet.title',   descKey: 'seo.closet.description' },
  ...
};

export function SeoBase({ pathname }) {
  const { t } = useTranslation();
  const entry = META[pathname] || META['/'];
  return (
    <Helmet>
      <title>{t(entry.titleKey)}</title>
      <meta name="description" content={t(entry.descKey)} />
    </Helmet>
  );
}
```

The auto-patcher does NOT touch SeoBase.jsx — these are listed as
manual-fix candidates.

---

## 4. Country list in `src/lib/countries.js` (250 ISO names)

This is a 250-entry `[{ code: 'AF', name: 'Afghanistan' }, …]` array exported
as a constant. **The audit deliberately skipped this file** — translating
country names through the same i18n dictionary as UI copy bloats every locale
file by ~6 KB.

**Recommended pattern (no LLM translation needed):**

```js
// Use the browser's built-in localised country names
function localisedCountryName(code, lang) {
  try {
    return new Intl.DisplayNames([lang], { type: 'region' }).of(code);
  } catch {
    return code;
  }
}
```

`Intl.DisplayNames` is supported in every modern browser and ships with
correct translations for all 200+ countries in every locale — zero
maintenance cost.

---

## Summary of files needing manual code patches

| File | Cases | Effort |
|---|---|---|
| `src/pages/ListingDetail.jsx` | 4 chip patches (1a–1d) | ~10 min |
| `src/pages/Home.jsx` | Trend bucket map + fallback constant restructure | ~20 min |
| `src/components/SeoBase.jsx` | META → i18n keys refactor | ~15 min |
| `src/lib/countries.js` | Adopt `Intl.DisplayNames` | ~5 min |

Total: ~50 minutes of manual code work to close the gap that translation
alone cannot reach.
