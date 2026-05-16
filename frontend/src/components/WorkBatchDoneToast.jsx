/**
 * WorkBatchDoneToast.jsx — bridges the global ``workStore`` to the
 * ``sonner`` toaster.
 *
 * Patch M20 (May 2026) — Pops a single "You have news in your
 * closet" toast each time a polish batch fully drains, regardless of
 * which page the user is on. The toast clicks through to /closet so
 * they can see the freshly-polished thumbnails.
 *
 * This is kept separate from ``WorkProgressFloater`` because the
 * floater is purely visual whereas the toast has a side effect
 * (firing global UI). Splitting also makes it easy to disable just
 * one or the other for triage.
 */

import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { workStore } from '@/lib/workStore';

export function WorkBatchDoneToast() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  useEffect(() => {
    return workStore.onBatchDone(({ total, completed }) => {
      if (!total) return; // No-op for empty drains.
      toast.success(
        t('floater.batchDoneTitle', {
          defaultValue: 'You have news in your closet',
        }),
        {
          description: t('floater.batchDoneDescription', {
            defaultValue:
              '{{n}} of {{m}} freshly-polished item(s) ready to view',
            n: completed,
            m: total,
          }),
          action: {
            label: t('floater.batchDoneCta', {
              defaultValue: 'Open closet',
            }),
            onClick: () => navigate('/closet'),
          },
          duration: 6000,
        },
      );
    });
  }, [navigate, t]);

  return null;
}
