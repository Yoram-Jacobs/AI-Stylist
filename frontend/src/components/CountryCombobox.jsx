import { useMemo, useState } from 'react';
import { Check, ChevronsUpDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { COUNTRIES, flagEmoji, resolveCountry } from '@/lib/countries';
import { cn } from '@/lib/utils';

/**
 * Type-to-filter country picker.
 *
 * Stores the free-text country **name** in the parent form state
 * (matching what the address payload has historically contained —
 * we never store an ISO code as the source of truth, just resolve
 * to one for display and for biasing geocoder lookups). This keeps
 * the change non-breaking for the backend `User.address.country`
 * field which is plain text on every existing row.
 *
 * UX:
 * - Click → popover with searchable list (cmdk handles fuzzy matching).
 * - Each row shows flag + localised display name (when the active
 *   i18n locale exposes a region translator), with the English name
 *   as a secondary hint.
 * - Falls back to a passthrough free-text input via the popover
 *   search so the user can type any free-form country we don't have
 *   in our 250-row dataset.
 *
 * Props:
 *   value: current country string (free text — name preferred).
 *   onChange: receives the next country **name** (string).
 *   onCodeChange?: optional callback receiving the ISO-2 code (or
 *     `null` if the value didn't resolve) — useful to bias the
 *     downstream city/street geocoder.
 *   placeholder, disabled, testid: standard form props.
 */
export function CountryCombobox({
  value,
  onChange,
  onCodeChange,
  placeholder,
  disabled,
  testid,
}) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);

  // Optional localisation of country names via Intl.DisplayNames.
  // Falls back silently to the bundled English names when the
  // browser doesn't support the active locale's region table.
  const displayNames = useMemo(() => {
    try {
      return new Intl.DisplayNames([i18n.language || 'en'], { type: 'region' });
    } catch {
      return null;
    }
  }, [i18n.language]);

  const localised = useMemo(
    () =>
      COUNTRIES.map((c) => ({
        ...c,
        localName: displayNames ? displayNames.of(c.code) || c.name : c.name,
      })),
    [displayNames],
  );

  const resolved = resolveCountry(value);
  const display = resolved
    ? `${flagEmoji(resolved.code)}  ${
        displayNames ? displayNames.of(resolved.code) || resolved.name : resolved.name
      }`
    : value || '';

  const select = (next) => {
    onChange(next.name);
    onCodeChange?.(next.code);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className={cn(
            'w-full justify-between rounded-xl font-normal',
            !value && 'text-muted-foreground',
          )}
          data-testid={testid}
        >
          <span className="truncate">
            {display || placeholder || t('profile.countryPlaceholder')}
          </span>
          <ChevronsUpDown className="ms-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command
          // cmdk's built-in filter does substring match on the localised
          // name, the English name, AND the ISO code (we lowercase the
          // value so it stays case-insensitive across all three).
          filter={(itemValue, search) =>
            itemValue.toLowerCase().includes(search.toLowerCase()) ? 1 : 0
          }
        >
          <CommandInput
            placeholder={t('profile.countrySearch')}
            data-testid={`${testid}-search`}
          />
          <CommandList>
            <CommandEmpty>
              {t('profile.countryEmpty', { defaultValue: 'No country found.' })}
            </CommandEmpty>
            <CommandGroup>
              {localised.map((c) => {
                // Composite value lets cmdk match against name OR
                // ISO code OR English fallback — type "DE" or "alle"
                // and you'll find Germany either way.
                const itemValue = `${c.localName} ${c.name} ${c.code}`;
                return (
                  <CommandItem
                    key={c.code}
                    value={itemValue}
                    onSelect={() => select(c)}
                    data-testid={`country-option-${c.code}`}
                  >
                    <span className="me-2 text-base leading-none">
                      {flagEmoji(c.code)}
                    </span>
                    <span className="truncate">{c.localName}</span>
                    {c.localName !== c.name && (
                      <span className="ms-2 text-xs text-muted-foreground truncate">
                        {c.name}
                      </span>
                    )}
                    <Check
                      className={cn(
                        'ms-auto h-4 w-4',
                        resolved?.code === c.code ? 'opacity-100' : 'opacity-0',
                      )}
                    />
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

export default CountryCombobox;
