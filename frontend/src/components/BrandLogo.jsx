import React from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

/**
 * DressApp brand lockup: the new figure-in-circle mark (served from
 * /apple-touch-icon.png so it's always available without bundling a
 * second copy into the JS bundle) placed to the left of the Gloock
 * serif wordmark.
 *
 * Sizing is controlled via the ``size`` prop so the same component
 * works in the small TopNav slot (text-2xl) and the large login
 * editorial panel (text-3xl) without re-implementing the markup in
 * each location.
 */
export function BrandLogo({ className, size = 'md', showWordmark = true, testId = 'brand-logo' }) {
  const { t } = useTranslation();
  // Map the size prop to matching mark height + text class. Keeping
  // both in one table makes it obvious the two scale together.
  const sizing = {
    sm: { markH: 'h-6', wordClass: 'text-xl' },
    md: { markH: 'h-7', wordClass: 'text-2xl' },
    lg: { markH: 'h-9', wordClass: 'text-3xl' },
    xl: { markH: 'h-12', wordClass: 'text-4xl' },
  }[size] || { markH: 'h-7', wordClass: 'text-2xl' };

  return (
    <span
      className={cn('inline-flex items-center gap-2.5 select-none', className)}
      data-testid={testId}
    >
      <img
        src="/apple-touch-icon.png"
        alt={t('brand', { defaultValue: 'DressApp' })}
        className={cn(sizing.markH, 'w-auto shrink-0 drop-shadow-sm')}
        loading="eager"
        decoding="async"
      />
      {showWordmark && (
        <span className={cn('font-display leading-none', sizing.wordClass)}>
          {t('brand', { defaultValue: 'DressApp' })}
        </span>
      )}
    </span>
  );
}

export default BrandLogo;
