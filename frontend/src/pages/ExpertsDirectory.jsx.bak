import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  Search as SearchIcon,
  Globe,
  Phone,
  Mail,
  MapPin,
  UserRound,
  Sparkles,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useLocation } from '@/lib/location';
import { AdTicker } from '@/components/AdTicker';
import { useAuth } from '@/lib/auth';
import { expertsStore } from '@/lib/expertsStore';
import { useCachedList } from '@/lib/createCachedStore';

/**
 * Experts directory — public-facing list of self-certified fashion pros.
 * Pre-filters by viewer's country when LocationProvider has coordinates.
 */
export default function ExpertsDirectory() {
  const { t } = useTranslation();
  const loc = useLocation?.();
  const { user } = useAuth();
  // Two-state filter pattern: ``draft`` is bound to the inputs (every
  // keystroke), ``applied`` is the snapshot the cached store fetches.
  // We only promote ``draft -> applied`` when the user clicks Search,
  // hits Enter, or clears. Initial ``applied`` is the empty filter
  // set so we hit the same cache slot the AppLayout prewarm warmed.
  const [draft, setDraft] = useState({
    profession: '',
    country: '',
    region: '',
    q: '',
  });
  const [applied, setApplied] = useState({
    profession: '',
    country: '',
    region: '',
    q: '',
  });

  // Pre-seed country & region from device location on first mount.
  // We seed only the *draft* — the user still has to apply it. This
  // keeps the prewarmed default-view cache hit on first paint and
  // gives the user an immediate hint of what filters might be useful.
  useEffect(() => {
    if (!loc) return;
    setDraft((f) => ({
      ...f,
      country: f.country || loc.country_code || loc.country || '',
      region: f.region || loc.city || '',
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loc?.country_code, loc?.city]);

  const expertParams = useMemo(() => {
    const p = {};
    if (applied.profession) p.profession = applied.profession;
    if (applied.country) p.country = applied.country;
    if (applied.region) p.region = applied.region;
    if (applied.q) p.q = applied.q;
    return p;
  }, [applied.profession, applied.country, applied.region, applied.q]);

  const { items, total, loading } = useCachedList(expertsStore, expertParams);

  const apply = () => setApplied({ ...draft });
  const clear = () => {
    const empty = { profession: '', country: '', region: '', q: '' };
    setDraft(empty);
    setApplied(empty);
  };

  const professions = useMemo(() => {
    const set = new Set((items || []).map((p) => p.professional?.profession).filter(Boolean));
    return Array.from(set);
  }, [items]);

  const viewerIsPro = !!user?.professional?.is_professional;
  // Show the skeleton only when we have nothing cached yet.
  const showSkeleton = loading && (!items || items.length === 0);

  return (
    <div className="min-h-full">
      <div className="container-px max-w-6xl mx-auto pt-6 md:pt-10">
        <div className="flex items-end justify-between gap-4 mb-6 flex-wrap">
          <div>
            <div className="caps-label text-muted-foreground">{t('nav.experts')}</div>
            <h1
              className="font-display text-3xl sm:text-4xl mt-1"
              data-testid="experts-title"
            >
              {t('experts.title')}
            </h1>
            <p className="text-sm text-muted-foreground mt-2 max-w-xl">
              {t('experts.subtitle')}
            </p>
          </div>
          <Badge
            variant="outline"
            className="rounded-full bg-card caps-label"
            data-testid="experts-count-badge"
          >
            {t('experts.countLabel', { count: total })}
          </Badge>
        </div>

        {/* --- Filters --- */}
        <Card
          className="rounded-[calc(var(--radius)+6px)] shadow-editorial mb-6"
          data-testid="experts-filter-card"
        >
          <CardContent className="p-5">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div>
                <Label className="caps-label text-muted-foreground">
                  {t('experts.filters.search')}
                </Label>
                <div className="relative mt-1">
                  <SearchIcon className="absolute start-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    value={draft.q}
                    onChange={(e) => setDraft({ ...draft, q: e.target.value })}
                    onKeyDown={(e) => e.key === 'Enter' && apply()}
                    className="ps-9 rounded-xl"
                    placeholder={t('experts.filters.search')}
                    data-testid="experts-filter-search"
                  />
                </div>
              </div>
              <div>
                <Label className="caps-label text-muted-foreground">
                  {t('experts.filters.profession')}
                </Label>
                <Input
                  list="experts-profession-suggestions"
                  value={draft.profession}
                  onChange={(e) =>
                    setDraft({ ...draft, profession: e.target.value })
                  }
                  onKeyDown={(e) => e.key === 'Enter' && apply()}
                  className="mt-1 rounded-xl"
                  placeholder={t('experts.filters.anyProfession')}
                  data-testid="experts-filter-profession"
                />
                <datalist id="experts-profession-suggestions">
                  {professions.map((p) => (
                    <option key={p} value={p} />
                  ))}
                </datalist>
              </div>
              <div>
                <Label className="caps-label text-muted-foreground">
                  {t('experts.filters.country')}
                </Label>
                <Input
                  value={draft.country}
                  onChange={(e) =>
                    setDraft({ ...draft, country: e.target.value })
                  }
                  onKeyDown={(e) => e.key === 'Enter' && apply()}
                  className="mt-1 rounded-xl"
                  placeholder="IL, US, FR…"
                  data-testid="experts-filter-country"
                />
              </div>
              <div>
                <Label className="caps-label text-muted-foreground">
                  {t('experts.filters.region')}
                </Label>
                <Input
                  value={draft.region}
                  onChange={(e) =>
                    setDraft({ ...draft, region: e.target.value })
                  }
                  onKeyDown={(e) => e.key === 'Enter' && apply()}
                  className="mt-1 rounded-xl"
                  data-testid="experts-filter-region"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <Button
                onClick={apply}
                disabled={loading}
                className="rounded-xl"
                data-testid="experts-apply-filters"
              >
                {t('common.search') || 'Search'}
              </Button>
              <Button
                variant="secondary"
                onClick={clear}
                disabled={loading}
                className="rounded-xl"
                data-testid="experts-clear-filters"
              >
                {t('experts.filters.clear')}
              </Button>
              {!viewerIsPro && (
                <Link
                  to="/me"
                  className="ms-auto text-xs text-[hsl(var(--accent))] self-center"
                  data-testid="experts-become-pro-cta"
                >
                  <Sparkles className="inline h-3 w-3 me-1" />
                  {t('experts.becomeExpertCta')}
                </Link>
              )}
            </div>
          </CardContent>
        </Card>

        {/* --- Grid --- */}
        {showSkeleton ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton
                key={i}
                className="h-48 w-full rounded-[calc(var(--radius)+6px)]"
              />
            ))}
          </div>
        ) : items.length === 0 ? (
          <Card
            className="rounded-[calc(var(--radius)+6px)] shadow-editorial"
            data-testid="experts-empty"
          >
            <CardContent className="p-10 text-center">
              <UserRound className="h-8 w-8 mx-auto text-muted-foreground" />
              <h3 className="font-display text-xl mt-3">
                {t('experts.emptyTitle')}
              </h3>
              <p className="text-sm text-muted-foreground mt-1 max-w-sm mx-auto">
                {t('experts.emptyBody')}
              </p>
            </CardContent>
          </Card>
        ) : (
          <div
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
            data-testid="experts-grid"
          >
            {items.map((p) => (
              <ExpertCard key={p.id} expert={p} />
            ))}
          </div>
        )}

        <div className="h-10" />
      </div>

      {/* --- Regional ad ticker at the bottom of the directory --- */}
      <AdTicker placement="experts" className="mt-6" />
    </div>
  );
}

function ExpertCard({ expert }) {
  const { t } = useTranslation();
  const prof = expert.professional || {};
  const biz = prof.business || {};
  const city =
    expert.home_location?.city ||
    expert.address?.city ||
    expert.address?.region ||
    expert.home_location?.country ||
    expert.address?.country;

  const avatar = expert.face_photo_url || expert.avatar_url;

  return (
    <Card
      className="rounded-[calc(var(--radius)+6px)] shadow-editorial h-full flex flex-col"
      data-testid={`expert-card-${expert.id}`}
    >
      <CardContent className="p-5 flex-1 flex flex-col">
        <div className="flex items-start gap-3">
          <div className="h-12 w-12 rounded-xl bg-secondary border border-border overflow-hidden shrink-0">
            {avatar ? (
              <img
                src={avatar}
                alt={expert.display_name}
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="h-full w-full inline-flex items-center justify-center text-muted-foreground">
                <UserRound className="h-5 w-5" />
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="font-display text-lg truncate">
              {expert.display_name}
            </h3>
            {prof.profession && (
              <Badge
                variant="outline"
                className="rounded-full text-[10px] bg-card mt-0.5"
              >
                {prof.profession}
              </Badge>
            )}
            {biz.name && (
              <div className="text-sm text-muted-foreground mt-1 truncate">
                {biz.name}
              </div>
            )}
          </div>
        </div>

        {biz.description && (
          <p className="text-sm text-muted-foreground mt-3 line-clamp-3">
            {biz.description}
          </p>
        )}

        <div className="mt-auto pt-4 space-y-1 text-xs text-muted-foreground">
          {city && (
            <div className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3" />
              {city}
            </div>
          )}
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {biz.website && (
            <Button
              asChild
              size="sm"
              variant="outline"
              className="rounded-full"
              data-testid={`expert-${expert.id}-website`}
            >
              <a
                href={biz.website}
                target="_blank"
                rel="noopener noreferrer"
              >
                <Globe className="h-3 w-3 me-1" />
                {t('experts.visitWebsite')}
              </a>
            </Button>
          )}
          {biz.phone && (
            <Button
              asChild
              size="sm"
              variant="outline"
              className="rounded-full"
              data-testid={`expert-${expert.id}-phone`}
            >
              <a href={`tel:${biz.phone}`}>
                <Phone className="h-3 w-3 me-1" />
                {t('experts.callNow')}
              </a>
            </Button>
          )}
          {biz.email && (
            <Button
              asChild
              size="sm"
              variant="outline"
              className="rounded-full"
              data-testid={`expert-${expert.id}-email`}
            >
              <a href={`mailto:${biz.email}`}>
                <Mail className="h-3 w-3 me-1" />
                {t('experts.sendEmail')}
              </a>
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
