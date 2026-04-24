import { useTranslation } from 'react-i18next';
import {
  BadgeCheck,
  ExternalLink,
  Globe2,
  Leaf,
  QrCode,
  Wrench,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';

/**
 * DppPanel — renders a closet item's EU Digital Product Passport data.
 *
 * Safe to render with sparse or empty data: each sub-section only shows
 * when the corresponding field is present. When the entire dpp_data blob
 * is absent or has only a parse_error, the component renders nothing.
 */
export const DppPanel = ({ dppData }) => {
  const { t } = useTranslation();
  if (!dppData) return null;
  const {
    gtin,
    country_of_origin: countryOfOrigin,
    materials_normalised: materials,
    carbon_footprint: carbonFootprint,
    care_instructions: careInstructions,
    repair_instructions: repairInstructions,
    certifications,
    source_url: sourceUrl,
    parse_error: parseError,
  } = dppData;

  // Nothing meaningful to render.
  const hasAny =
    gtin ||
    countryOfOrigin ||
    (materials && materials.length) ||
    carbonFootprint ||
    (careInstructions && careInstructions.length) ||
    (repairInstructions && repairInstructions.length) ||
    (certifications && certifications.length) ||
    sourceUrl;
  if (!hasAny || parseError) return null;

  const formatCarbon = () => {
    if (!carbonFootprint) return null;
    if (typeof carbonFootprint === 'string') return carbonFootprint;
    if (typeof carbonFootprint === 'number') return `${carbonFootprint} kg CO₂e`;
    if (typeof carbonFootprint === 'object') {
      const value = carbonFootprint.value ?? carbonFootprint.amount;
      const unit = carbonFootprint.unit || 'kg CO₂e';
      if (value != null) return `${value} ${unit}`;
    }
    return null;
  };

  const carbon = formatCarbon();

  return (
    <Card
      className="rounded-[calc(var(--radius)+6px)] shadow-editorial border-[hsl(var(--accent))]/30"
      data-testid="item-dpp-panel"
    >
      <CardContent className="p-5 space-y-4">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="caps-label text-muted-foreground flex items-center gap-1.5">
              <QrCode className="h-3.5 w-3.5 text-[hsl(var(--accent))]" />
              {t('dpp.panel.title')}
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              {t('dpp.panel.subtitle')}
            </p>
          </div>
        </div>

        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          {gtin && (
            <div data-testid="dpp-field-gtin">
              <dt className="text-xs text-muted-foreground">
                {t('dpp.panel.gtin')}
              </dt>
              <dd className="font-mono text-sm tracking-wider mt-0.5">{gtin}</dd>
            </div>
          )}
          {countryOfOrigin && (
            <div data-testid="dpp-field-country">
              <dt className="text-xs text-muted-foreground flex items-center gap-1">
                <Globe2 className="h-3 w-3" />
                {t('dpp.panel.countryOfOrigin')}
              </dt>
              <dd className="mt-0.5">{countryOfOrigin}</dd>
            </div>
          )}
          {carbon && (
            <div data-testid="dpp-field-carbon">
              <dt className="text-xs text-muted-foreground flex items-center gap-1">
                <Leaf className="h-3 w-3 text-[hsl(var(--accent))]" />
                {t('dpp.panel.carbonFootprint')}
              </dt>
              <dd className="mt-0.5">{carbon}</dd>
            </div>
          )}
        </dl>

        {materials && materials.length > 0 && (
          <div data-testid="dpp-field-materials">
            <div className="text-xs text-muted-foreground mb-1.5">
              {t('dpp.panel.materials')}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {materials.map((m, i) => (
                <Badge
                  key={`${m.name || m.tag}-${i}`}
                  variant="outline"
                  className="rounded-full text-xs font-normal"
                >
                  {m.pct != null
                    ? `${m.pct}% ${m.name || m.tag}`
                    : (m.name || m.tag)}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {certifications && certifications.length > 0 && (
          <div data-testid="dpp-field-certifications">
            <div className="text-xs text-muted-foreground mb-1.5 flex items-center gap-1">
              <BadgeCheck className="h-3 w-3 text-[hsl(var(--accent))]" />
              {t('dpp.panel.certifications')}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {certifications.map((c, i) => (
                <Badge
                  key={`${c}-${i}`}
                  className="rounded-full text-xs bg-[hsl(var(--accent))]/10 text-[hsl(var(--accent))] border-[hsl(var(--accent))]/30 hover:bg-[hsl(var(--accent))]/20"
                  variant="outline"
                >
                  {c}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {careInstructions && careInstructions.length > 0 && (
          <div data-testid="dpp-field-care">
            <div className="text-xs text-muted-foreground mb-1.5">
              {t('dpp.panel.careInstructions')}
            </div>
            <ul className="text-sm space-y-0.5 list-disc ps-5">
              {careInstructions.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </div>
        )}

        {repairInstructions && repairInstructions.length > 0 && (
          <div data-testid="dpp-field-repair">
            <div className="text-xs text-muted-foreground mb-1.5 flex items-center gap-1">
              <Wrench className="h-3 w-3" />
              {t('dpp.panel.repairInstructions')}
            </div>
            <ul className="text-sm space-y-0.5 list-disc ps-5">
              {repairInstructions.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        )}

        {sourceUrl && (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1.5 text-xs text-[hsl(var(--accent))] hover:underline"
            data-testid="dpp-field-source-url"
          >
            <ExternalLink className="h-3 w-3" />
            {t('dpp.panel.sourceLink')}
          </a>
        )}
      </CardContent>
    </Card>
  );
};

export default DppPanel;
