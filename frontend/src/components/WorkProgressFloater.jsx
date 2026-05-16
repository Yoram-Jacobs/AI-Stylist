/**
 * WorkProgressFloater.jsx — bottom-right pill that shows in-flight
 * /analyze + polish work across page navigations.
 *
 * Patch M20 (May 2026) — Subscribes to the global ``workStore`` and
 * renders a compact glass-morphism pill whenever there's activity.
 * The pill auto-hides ~500 ms after the last job drains so the user
 * gets a visible "done" beat without it lingering forever.
 */

import { useSyncExternalStore, useEffect, useState } from 'react';
import { Sparkles, Shirt } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { workStore } from '@/lib/workStore';

export function WorkProgressFloater() {
  const { t } = useTranslation();
  const state = useSyncExternalStore(
    workStore.subscribe,
    workStore.getSnapshot,
    workStore.getSnapshot,
  );

  // Linger a moment after the last job drains so the pill doesn't
  // vanish the instant the final percentage hits 100. Pure
  // affordance — gives the user time to register "done".
  const [linger, setLinger] = useState(false);
  const analyzeCount = Object.keys(state.analyzeJobs).length;
  const polishTotal = state.polishBatchTotal;
  const polishDone = state.polishBatchCompleted;
  const polishPending = state.polishPendingIds.size;
  const active = analyzeCount > 0 || polishPending > 0;

  useEffect(() => {
    if (active) {
      setLinger(true);
      return undefined;
    }
    // No active work — schedule a fade-out.
    const handle = setTimeout(() => setLinger(false), 1200);
    return () => clearTimeout(handle);
  }, [active]);

  if (!active && !linger) return null;

  // Aggregate the analyze progress across all running jobs so the
  // pill shows a single line of text instead of N stacked rows.
  const analyzeItems = Object.values(state.analyzeJobs).reduce(
    (acc, j) => acc + (j.items || 0),
    0,
  );
  const analyzeExpected = Object.values(state.analyzeJobs).reduce(
    (acc, j) => acc + (j.total || 0),
    0,
  );
  const analyzeLabel =
    analyzeExpected > 0
      ? t('floater.analyzing', {
          defaultValue: 'Analysing {{n}}/{{m}} items',
          n: analyzeItems,
          m: analyzeExpected,
        })
      : t('floater.analyzingPhotos', {
          defaultValue: 'Analysing {{count}} photo',
          count: analyzeCount,
        });

  const polishLabel =
    polishTotal > 0
      ? t('floater.polishing', {
          defaultValue: 'Polishing {{n}}/{{m}} photos',
          n: polishDone,
          m: polishTotal,
        })
      : t('floater.polishingMore', {
          defaultValue: 'Polishing {{count}} photo',
          count: polishPending,
        });

  const polishPct =
    polishTotal > 0 ? Math.min(100, Math.round((polishDone / polishTotal) * 100)) : 0;
  const analyzePct =
    analyzeExpected > 0
      ? Math.min(100, Math.round((analyzeItems / analyzeExpected) * 100))
      : 0;

  return (
    <div
      data-testid="work-progress-floater"
      className="fixed bottom-4 right-4 z-50 pointer-events-none"
    >
      <div
        className={
          'pointer-events-auto rounded-2xl border border-border bg-card/95 ' +
          'shadow-lg backdrop-blur-xl px-4 py-3 min-w-[220px] max-w-[320px] ' +
          'transition-opacity duration-300 ' +
          (active ? 'opacity-100' : 'opacity-70')
        }
      >
        {analyzeCount > 0 && (
          <div className="flex flex-col gap-1.5 mb-2" data-testid="floater-analyze">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Sparkles className="h-3.5 w-3.5 text-primary animate-pulse" aria-hidden />
              <span className="truncate">{analyzeLabel}</span>
            </div>
            <div
              className="h-1 rounded-full bg-muted overflow-hidden"
              role="progressbar"
              aria-valuenow={analyzePct}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="h-full bg-primary transition-all duration-300"
                style={{ width: `${Math.max(5, analyzePct)}%` }}
              />
            </div>
          </div>
        )}
        {polishPending > 0 && (
          <div className="flex flex-col gap-1.5" data-testid="floater-polish">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <Shirt className="h-3.5 w-3.5 text-primary animate-pulse" aria-hidden />
              <span className="truncate">{polishLabel}</span>
            </div>
            <div
              className="h-1 rounded-full bg-muted overflow-hidden"
              role="progressbar"
              aria-valuenow={polishPct}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="h-full bg-primary transition-all duration-300"
                style={{ width: `${Math.max(5, polishPct)}%` }}
              />
            </div>
          </div>
        )}
        {!active && (
          // Brief "all done" beat just before fade-out.
          <div className="flex items-center gap-2 text-sm font-medium text-foreground/70">
            <span aria-hidden>✓</span>
            <span>{t('floater.done', { defaultValue: 'All done' })}</span>
          </div>
        )}
      </div>
    </div>
  );
}
