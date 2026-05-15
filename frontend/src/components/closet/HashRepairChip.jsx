/* eslint-disable react/prop-types */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * HashRepairChip — non-blocking, ambient progress affordance for the
 * Phase Z2.3 streaming closet-hash repair.
 *
 * Behaviour
 * =========
 *   * **Idle** → renders nothing (the chip is invisible until the
 *     server starts streaming).
 *   * **Running** → small pill with a slow-spin Sparkles icon and a
 *     live ``"Tuning duplicate detector… 47/300"`` line that ticks
 *     up as NDJSON events arrive. Width is fixed so the layout
 *     doesn't reflow on every increment.
 *   * **Just finished (with repairs)** → flips to a success
 *     variant with a CheckCircle2 icon and the per-category counts
 *     for ~3 s, then fades out and unmounts.
 *   * **Just finished (no repairs)** → fades out silently — no
 *     point telling the user nothing happened.
 *   * **Failed** → soft red pill with the error class name; fades
 *     out after ~5 s. Repair is best-effort so we don't escalate
 *     to a toast.
 *
 * The chip is intentionally subtle (text-xs, muted background) so
 * it lives next to the closet count without competing with the
 * page title. All decoration is theme-token driven — no hard-coded
 * colours.
 */
export function HashRepairChip({ progress }) {
  const { t } = useTranslation();
  const [phase, setPhase] = useState('idle'); // idle | running | success | failure
  const [visible, setVisible] = useState(false);

  const running = !!progress?.running;
  const hasError = !!progress?.lastError;
  const repaired = progress?.repaired || 0;
  const cleared = progress?.cleared || 0;
  const failed = progress?.failed || 0;
  const scanned = progress?.scanned || 0;
  const total = progress?.total || 0;
  const lastRunAt = progress?.lastRunAt || 0;

  useEffect(() => {
    if (running) {
      setPhase('running');
      setVisible(true);
      return undefined;
    }
    if (hasError) {
      setPhase('failure');
      setVisible(true);
      const id = setTimeout(() => setVisible(false), 5000);
      return () => clearTimeout(id);
    }
    if (lastRunAt && (repaired > 0 || cleared > 0)) {
      setPhase('success');
      setVisible(true);
      const id = setTimeout(() => setVisible(false), 3500);
      return () => clearTimeout(id);
    }
    // Repair finished with nothing to do — fade silently.
    setVisible(false);
    return undefined;
    // We *intentionally* don't re-run on every progress tick — only on
    // ``running`` / ``lastRunAt`` / ``hasError`` transitions. The
    // running label below reads ``scanned``/``total`` directly each
    // render so the counter ticks without resetting the timeout.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, hasError, lastRunAt]);

  if (!visible) return null;

  const label = (() => {
    if (phase === 'running') {
      return t(
        'closet.repair.running',
        'Tuning duplicate detector… {{n}}/{{total}}',
        { n: scanned, total: total || '?' },
      );
    }
    if (phase === 'success') {
      const parts = [];
      if (repaired > 0) {
        parts.push(
          t('closet.repair.repaired', '{{n}} refreshed', { n: repaired }),
        );
      }
      if (cleared > 0) {
        parts.push(
          t('closet.repair.cleared', '{{n}} cleared', { n: cleared }),
        );
      }
      return parts.join(' · ') || t('closet.repair.doneEmpty', 'All set');
    }
    if (phase === 'failure') {
      return t('closet.repair.failed', 'Couldn’t refresh fingerprints');
    }
    return '';
  })();

  return (
    <span
      role="status"
      aria-live="polite"
      data-testid="closet-hash-repair-chip"
      data-phase={phase}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full',
        'px-2.5 py-1 text-xs font-medium',
        'border transition-opacity duration-300',
        'select-none whitespace-nowrap',
        phase === 'running' &&
          'border-border bg-secondary/60 text-foreground/80',
        phase === 'success' &&
          'border-[hsl(var(--accent))]/40 bg-[hsl(var(--accent))]/10 text-[hsl(var(--accent-foreground))]',
        phase === 'failure' &&
          'border-destructive/40 bg-destructive/10 text-destructive',
      )}
    >
      {phase === 'running' || phase === 'failure' ? (
        <Sparkles
          className={cn(
            'h-3.5 w-3.5',
            phase === 'running' && 'animate-pulse',
          )}
          aria-hidden="true"
        />
      ) : (
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      <span>{label}</span>
      {phase === 'running' && failed > 0 ? (
        <span
          className="text-destructive/80 ms-1"
          aria-label={t('closet.repair.failedCount', '{{n}} failed', { n: failed })}
        >
          · {failed}!
        </span>
      ) : null}
    </span>
  );
}
