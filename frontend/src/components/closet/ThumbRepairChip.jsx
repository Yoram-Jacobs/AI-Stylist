/* eslint-disable react/prop-types */
import { useTranslation } from 'react-i18next';
import { StreamingProgressChip } from '@/components/StreamingProgressChip';

/**
 * ThumbRepairChip — domain wrapper around ``StreamingProgressChip``
 * for the Phase Z2.6 closet-thumbnail repair stream.
 *
 * Twin of ``HashRepairChip``. Renders nothing while idle. Ticks
 * progress live while a pass is running (``regenerated``/``failed``
 * counters tick on each NDJSON event). On completion: success chip
 * fades after 3.5 s iff at least one row was regenerated, otherwise
 * silently disappears.
 *
 * Sits next to ``HashRepairChip`` in the closet header — both pass
 * in different ``progress`` snapshots and can fire back-to-back
 * (hashes first, thumbnails second) without colliding.
 */
export function ThumbRepairChip({ progress }) {
  const { t } = useTranslation();

  const scanned = progress?.scanned || 0;
  const total = progress?.total || 0;
  const regenerated = progress?.regenerated || 0;

  const runningLabel = t(
    'closet.thumbRepair.running',
    'Refreshing thumbnails… {{n}}/{{total}}',
    { n: scanned, total: total || '?' },
  );

  const successLabel =
    regenerated > 0
      ? t('closet.thumbRepair.regenerated', '{{n}} refreshed', {
          n: regenerated,
        })
      : '';

  const failureLabel = t(
    'closet.thumbRepair.failed',
    'Couldn’t refresh thumbnails',
  );

  return (
    <StreamingProgressChip
      progress={progress}
      runningLabel={runningLabel}
      successLabel={successLabel}
      failureLabel={failureLabel}
      hasSuccessChanges={(p) => (p?.regenerated || 0) > 0}
      testId="closet-thumb-repair-chip"
    />
  );
}
