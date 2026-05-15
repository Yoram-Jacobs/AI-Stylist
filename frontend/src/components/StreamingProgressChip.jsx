/* eslint-disable react/prop-types */
import { useEffect, useState } from 'react';
import { Sparkles, CheckCircle2, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * StreamingProgressChip — ambient, non-blocking progress affordance
 * for any NDJSON-streaming server → client sync.
 *
 * Designed to live next to a page title (or any spot where a small
 * pill of status is welcome) and stay out of the way otherwise.
 *
 * Phases
 * ======
 *   * **idle**     → renders nothing.
 *   * **running**  → secondary-tinted pill, animated Sparkles, live
 *                    "{label} 47/300" counter that ticks on each
 *                    incoming NDJSON event without reflowing the
 *                    surrounding layout.
 *   * **success**  → accent-tinted pill, CheckCircle2, summary
 *                    text (e.g. "13 refreshed · 2 cleared") visible
 *                    for ~3.5 s then fades out.
 *   * **failure**  → destructive-tinted pill, AlertTriangle, error
 *                    text, fades out after ~5 s.
 *
 * Behaviour rules
 * ===============
 *   * If the stream finishes with no notable changes (no items in
 *     ``successCounts``), the chip fades silently — no point telling
 *     the user nothing happened.
 *   * Re-entering ``running`` while the success/failure timer is
 *     active **resets** to the running phase and cancels the timer.
 *   * All decoration is design-token driven (no hard-coded colours).
 *
 * Contract
 * ========
 *   ``progress``       Snapshot object from the parent store; this
 *                      component never mutates it. Shape:
 *                        {
 *                          running: boolean,
 *                          scanned: number,
 *                          total: number,
 *                          failed: number,
 *                          lastRunAt: number,   // epoch ms
 *                          lastError: string|null,
 *                          ...                  // any extra fields
 *                        }
 *   ``runningLabel``   Translated string for the running phase, with
 *                      optional ``{{n}}`` / ``{{total}}`` markers
 *                      pre-interpolated by the caller. The chip just
 *                      renders it verbatim — caller controls i18n.
 *   ``successLabel``   Translated string for the success phase.
 *                      Empty string ⇒ silent fade.
 *   ``failureLabel``   Translated string for the failure phase.
 *   ``hasSuccessChanges`` Optional ``() => boolean`` — when omitted,
 *                      the chip's success phase shows iff
 *                      ``successLabel`` is non-empty. When supplied,
 *                      the success phase shows iff this returns true
 *                      (e.g. ``progress.repaired + progress.cleared > 0``).
 *   ``testId``         data-testid root. Append ``-<phase>`` if you
 *                      want phase-specific selectors.
 *   ``className``      Optional extra Tailwind classes for the pill.
 */
export function StreamingProgressChip({
  progress,
  runningLabel,
  successLabel,
  failureLabel,
  hasSuccessChanges,
  testId = 'streaming-progress-chip',
  className,
}) {
  const [phase, setPhase] = useState('idle');
  const [visible, setVisible] = useState(false);

  const running = !!progress?.running;
  const hasError = !!progress?.lastError;
  const failed = progress?.failed || 0;
  const lastRunAt = progress?.lastRunAt || 0;
  const successWorthShowing = (() => {
    if (typeof hasSuccessChanges === 'function') {
      try { return !!hasSuccessChanges(progress); } catch { return false; }
    }
    return !!successLabel;
  })();

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
    if (lastRunAt && successWorthShowing) {
      setPhase('success');
      setVisible(true);
      const id = setTimeout(() => setVisible(false), 3500);
      return () => clearTimeout(id);
    }
    // Stream finished with nothing noteworthy — fade silently.
    setVisible(false);
    return undefined;
    // Re-running this effect on every counter tick would reset the
    // timeout; we deliberately depend only on transition keys.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, hasError, lastRunAt]);

  if (!visible) return null;

  const label = (
    phase === 'running' ? runningLabel
    : phase === 'success' ? successLabel
    : phase === 'failure' ? failureLabel
    : ''
  );

  return (
    <span
      role="status"
      aria-live="polite"
      data-testid={testId}
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
        className,
      )}
    >
      {phase === 'running' ? (
        <Sparkles className="h-3.5 w-3.5 animate-pulse" aria-hidden="true" />
      ) : phase === 'failure' ? (
        <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
      ) : (
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      <span>{label}</span>
      {phase === 'running' && failed > 0 ? (
        <span className="text-destructive/80 ms-1">· {failed}!</span>
      ) : null}
    </span>
  );
}
