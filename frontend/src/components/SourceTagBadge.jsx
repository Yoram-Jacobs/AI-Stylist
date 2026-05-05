import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { labelForSource, labelForIntent } from '@/lib/taxonomy';

// ---------------------------------------------------------------------
// Source / intent → visual style.
//
// "Shared" used to be a single catch-all badge for anything published
// to the marketplace. Now we surface the user's *actual* intent:
// "For sale" / "Swap" / "Donate" — so a glance at any closet card or
// listing card tells you what kind of marketplace activity it is.
//
// Color choices (all pulled from existing design tokens — no raw
// Tailwind colors per the design mandate):
//
//   • For sale  → persimmon (warm orange — commerce / money signal)
//   • Swap      → accent (teal — community exchange, current brand colour)
//   • Donate    → primary (dark, quiet — a "gift" tone, distinct from sale)
//   • Private   → secondary (neutral)
//   • Retail    → persimmon (existing behaviour, items not on marketplace
//                  so won't visually clash with For-sale listings)
// ---------------------------------------------------------------------
const SOURCE_STYLES = {
  Private: 'bg-secondary text-foreground border border-border',
  Shared:
    'bg-[hsl(var(--accent))]/10 text-[hsl(var(--accent))] border border-[hsl(var(--accent))]/30',
  Retail:
    'bg-[hsl(var(--persimmon))]/10 text-[hsl(var(--persimmon))] border border-[hsl(var(--persimmon))]/30',
};

const INTENT_STYLES = {
  for_sale:
    'bg-[hsl(var(--persimmon))]/10 text-[hsl(var(--persimmon))] border border-[hsl(var(--persimmon))]/30',
  swap:
    'bg-[hsl(var(--accent))]/10 text-[hsl(var(--accent))] border border-[hsl(var(--accent))]/30',
  donate:
    'bg-primary/10 text-primary border border-primary/30',
};

// Listings carry ``mode`` (``sell|swap|donate``); closet items carry
// ``marketplace_intent`` (``own|for_sale|swap|donate``). Normalise both
// into a single intent code so the badge has one mental model.
const _normalizeIntent = (intent, mode) => {
  if (intent && intent !== 'own') return intent;
  if (mode === 'sell') return 'for_sale';
  if (mode === 'swap' || mode === 'donate') return mode;
  return null;
};

export const SourceTagBadge = ({
  source = 'Private',
  intent,
  mode,
  className,
}) => {
  const { t } = useTranslation();

  // When an item is published to the marketplace ("Shared"), prefer
  // the more specific intent label/colour over the generic "Shared".
  const resolvedIntent =
    source === 'Shared' ? _normalizeIntent(intent, mode) : null;

  const style = resolvedIntent
    ? INTENT_STYLES[resolvedIntent] || SOURCE_STYLES.Shared
    : SOURCE_STYLES[source] || SOURCE_STYLES.Private;

  const label = resolvedIntent
    ? labelForIntent(resolvedIntent, t)
    : labelForSource(source, t);

  return (
    <Badge
      data-testid="source-tag-badge"
      data-intent={resolvedIntent || undefined}
      data-source={source}
      variant="outline"
      className={cn('rounded-full caps-label px-2.5 py-1 whitespace-nowrap', style, className)}
    >
      {label}
    </Badge>
  );
};
