/* eslint-disable react/prop-types */
import { useTranslation } from 'react-i18next';
import { StreamingProgressChip } from '@/components/StreamingProgressChip';

/**
 * HashRepairChip — domain wrapper around ``StreamingProgressChip``
 * for the Phase Z2.3 closet-hash repair stream.
 *
 * The chip-presentation logic (phases, fade-out timers, icons, theme
 * tokens) lives in ``StreamingProgressChip``. This thin file owns
 * **only** the i18n strings and the "what counts as a noteworthy
 * change for this stream?" rule (here: at least one ``repaired`` or
 * ``cleared`` row). Keeping the wrapper tiny means the marketplace
 * backfill / browse streams can reuse the same primitive without
 * dragging closet-specific copy through them.
 */
export function HashRepairChip({ progress }) {
  const { t } = useTranslation();

  const scanned = progress?.scanned || 0;
  const total = progress?.total || 0;
  const repaired = progress?.repaired || 0;
  const cleared = progress?.cleared || 0;

  const runningLabel = t(
    'closet.repair.running',
    'Tuning duplicate detector… {{n}}/{{total}}',
    { n: scanned, total: total || '?' },
  );

  const successParts = [];
  if (repaired > 0) {
    successParts.push(
      t('closet.repair.repaired', '{{n}} refreshed', { n: repaired }),
    );
  }
  if (cleared > 0) {
    successParts.push(
      t('closet.repair.cleared', '{{n}} cleared', { n: cleared }),
    );
  }
  const successLabel = successParts.join(' · ');

  const failureLabel = t(
    'closet.repair.failed',
    'Couldn’t refresh fingerprints',
  );

  return (
    <StreamingProgressChip
      progress={progress}
      runningLabel={runningLabel}
      successLabel={successLabel}
      failureLabel={failureLabel}
      hasSuccessChanges={(p) => (p?.repaired || 0) + (p?.cleared || 0) > 0}
      testId="closet-hash-repair-chip"
    />
  );
}
