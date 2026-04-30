import { useEffect, useRef, useState } from 'react';
import { Loader2, MapPin } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Input } from '@/components/ui/input';
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover';
import { cn } from '@/lib/utils';

/**
 * Debounced address autocomplete using OpenStreetMap Nominatim
 * (free, no API key, ~1 req/s rate limit per their usage policy).
 *
 * Used by the Settings → Contact section for the City and Street
 * (address line 1) fields. As the user types we hit Nominatim's
 * `/search` endpoint, biased to the selected country (`countrycodes`)
 * and the appropriate feature class (`featuretype=city|street`),
 * and surface up to 6 suggestions. Picking a suggestion fires
 * ``onSelect`` with a structured `{ city, region, postal_code,
 * country, country_code, line1 }` patch — the parent decides which
 * fields to merge into its form state.
 *
 * Why Nominatim and not Google Places / Mapbox?
 *   - No API key → no per-deploy secrets to add, no quota dashboard
 *     to monitor, works identically on every host.
 *   - Free for personal-use traffic levels (registration-form
 *     autocomplete is the textbook example of acceptable use).
 *   - The data is OpenStreetMap, which has worldwide coverage; quality
 *     is comparable to Google for street-level lookups in most
 *     populated places.
 *
 * Trade-off: Nominatim is slower than commercial geocoders (~300-800 ms
 * round-trip) and asks consumers to limit traffic to ~1 req/s. We
 * debounce by 400 ms which keeps us well under that, and we abort
 * any in-flight request the moment the user types another character.
 */
const NOMINATIM_BASE = 'https://nominatim.openstreetmap.org/search';
const DEBOUNCE_MS = 400;
const MIN_QUERY = 3;

export function AddressAutocomplete({
  value,
  onChange,
  onSelect,
  // 'city' | 'street'
  kind = 'city',
  // ISO-2 country code to bias search (optional but strongly
  // recommended — without it, "Springfield" is ambiguous).
  countryCode = null,
  placeholder,
  disabled,
  testid,
  inputId,
  autoComplete,
}) {
  const { t } = useTranslation();
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);
  const abortRef = useRef(null);
  // Set when the user picks a suggestion — used to suppress the
  // immediate re-fetch that would otherwise fire because the value
  // change re-triggers the effect.
  const justPickedRef = useRef(false);

  useEffect(() => {
    // Cancel previous in-flight request on every keystroke / unmount.
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    const q = (value || '').trim();
    if (justPickedRef.current) {
      justPickedRef.current = false;
      return;
    }
    if (q.length < MIN_QUERY) {
      setResults([]);
      setOpen(false);
      return;
    }
    const timer = setTimeout(async () => {
      // Abort any still-pending search before starting a new one.
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setLoading(true);
      try {
        const params = new URLSearchParams({
          q,
          format: 'json',
          addressdetails: '1',
          limit: '6',
          // 'accept-language' biases display names to the user's
          // browser locale so French users see "Allemagne" not "Germany".
          'accept-language': navigator.language || 'en',
        });
        if (countryCode) params.set('countrycodes', countryCode.toLowerCase());
        // 'featuretype' restricts the search to the right granularity:
        //   city → cities, towns, villages
        //   street → individual streets / addresses
        if (kind === 'city') params.set('featuretype', 'city');
        const r = await fetch(`${NOMINATIM_BASE}?${params.toString()}`, {
          signal: controller.signal,
          // Polite User-Agent override isn't possible from the browser
          // (it's a forbidden header), but Nominatim accepts the
          // default UA + the page's Referer for low-volume use.
          headers: { Accept: 'application/json' },
        });
        if (!r.ok) {
          setResults([]);
          return;
        }
        const data = await r.json();
        if (Array.isArray(data)) {
          setResults(data);
          setOpen(data.length > 0);
        }
      } catch (err) {
        if (err?.name !== 'AbortError') {
          // Silent — autocomplete failures shouldn't block the user
          // from saving a manually-typed address.
          // eslint-disable-next-line no-console
          console.debug('Nominatim search failed:', err);
        }
      } finally {
        setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [value, kind, countryCode]);

  const handlePick = (item) => {
    // Nominatim's `address` block uses many possible keys depending
    // on the place type — collapse the common ones into our flat
    // shape. The parent decides which fields to actually overwrite.
    const a = item.address || {};
    const cityValue =
      a.city || a.town || a.village || a.hamlet || a.municipality || '';
    const regionValue = a.state || a.region || a.county || '';
    const country = a.country || '';
    const countryCodeOut = (a.country_code || '').toUpperCase() || null;
    const postal = a.postcode || '';
    let streetLine = '';
    if (kind === 'street') {
      // Compose a sensible "Line 1" from house number + road. Some
      // providers return only one of the two — we tolerate both.
      const parts = [];
      if (a.house_number) parts.push(a.house_number);
      if (a.road) parts.push(a.road);
      streetLine = parts.join(' ').trim() || item.display_name?.split(',')[0] || '';
    }
    justPickedRef.current = true;
    onSelect?.({
      line1: streetLine,
      city: cityValue,
      region: regionValue,
      postal_code: postal,
      country,
      country_code: countryCodeOut,
    });
    setResults([]);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverAnchor asChild>
        <div className="relative">
          <Input
            ref={inputRef}
            id={inputId}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onFocus={() => results.length && setOpen(true)}
            placeholder={placeholder}
            disabled={disabled}
            autoComplete={autoComplete}
            className="rounded-xl pe-9"
            data-testid={testid}
          />
          {loading && (
            <Loader2 className="absolute end-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
          )}
        </div>
      </PopoverAnchor>
      <PopoverContent
        align="start"
        // Don't steal focus from the input — keeps typing flow natural.
        onOpenAutoFocus={(e) => e.preventDefault()}
        className="w-[--radix-popover-trigger-width] p-1"
      >
        <ul
          className="max-h-72 overflow-auto"
          role="listbox"
          data-testid={`${testid}-suggestions`}
        >
          {results.map((item) => {
            const a = item.address || {};
            const primary =
              kind === 'street'
                ? [a.house_number, a.road].filter(Boolean).join(' ') ||
                  item.display_name?.split(',')[0]
                : a.city || a.town || a.village || a.hamlet || item.display_name?.split(',')[0];
            const secondary = item.display_name
              ?.split(',')
              .slice(1)
              .join(',')
              .trim();
            return (
              <li
                key={item.place_id}
                className={cn(
                  'flex cursor-pointer items-start gap-2 rounded-lg px-2 py-1.5 text-sm',
                  'hover:bg-accent focus-visible:bg-accent',
                )}
                onClick={() => handlePick(item)}
                data-testid={`${testid}-suggestion`}
              >
                <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{primary}</div>
                  {secondary && (
                    <div className="truncate text-xs text-muted-foreground">
                      {secondary}
                    </div>
                  )}
                </div>
              </li>
            );
          })}
          {!loading && results.length === 0 && value?.length >= MIN_QUERY && (
            <li className="px-2 py-2 text-xs text-muted-foreground">
              {t('profile.addressNoResults', { defaultValue: 'No matches.' })}
            </li>
          )}
        </ul>
      </PopoverContent>
    </Popover>
  );
}

export default AddressAutocomplete;
