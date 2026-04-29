import { useTranslation } from 'react-i18next';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

/**
 * Editable list of weighted (name, %) entries — used for the rich
 * `colors` and `fabric_materials` taxonomy across both the Add Item
 * and Item Detail (edit) pages.
 *
 * Lives in `components/` (not co-located with a page) because both
 * pages render the exact same control: keeping a single source of
 * truth means the percentage validation (sum coloured red/green at
 * 100) and field shape stay consistent end-to-end.
 *
 * Props:
 *   label?: literal heading string (takes precedence over labelKey).
 *   labelKey?: i18n key for the heading.
 *   items: array of `{ name: string, pct: number|null }`.
 *   onChange: receives the next items array.
 *   placeholder: per-row name input placeholder.
 *   disabled: read-only mode.
 *   testid: prefix for `data-testid` on the rows + add button.
 */
export function WeightedList({
  label,
  labelKey,
  items,
  onChange,
  placeholder,
  disabled,
  testid,
}) {
  const { t } = useTranslation();
  const safe = Array.isArray(items) ? items : [];
  const sum = safe.reduce((s, it) => s + (Number(it.pct) || 0), 0);
  const update = (i, patch) =>
    onChange(safe.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  const remove = (i) => onChange(safe.filter((_, j) => j !== i));
  const add = () => onChange([...safe, { name: '', pct: 0 }]);
  const heading = labelKey ? t(labelKey) : label;
  return (
    <div>
      <div className="flex items-center justify-between">
        <Label className="caps-label text-muted-foreground">{heading}</Label>
        <span
          className={`text-[10px] font-mono ${
            sum === 100
              ? 'text-emerald-700'
              : sum > 100
              ? 'text-rose-700'
              : 'text-muted-foreground'
          }`}
        >
          {sum}%
        </span>
      </div>
      <div className="mt-1 space-y-1.5" data-testid={testid}>
        {safe.map((it, i) => (
          <div key={i} className="flex items-center gap-2">
            <Input
              value={it.name || ''}
              onChange={(e) => update(i, { name: e.target.value })}
              placeholder={placeholder}
              disabled={disabled}
              className="flex-1 rounded-xl h-9"
              data-testid={`${testid}-name-${i}`}
            />
            <Input
              type="number"
              min="0"
              max="100"
              value={it.pct ?? ''}
              onChange={(e) =>
                update(i, {
                  pct:
                    e.target.value === ''
                      ? null
                      : Math.max(0, Math.min(100, Number(e.target.value))),
                })
              }
              className="w-16 rounded-xl h-9 text-right"
              disabled={disabled}
              data-testid={`${testid}-pct-${i}`}
            />
            <span className="text-xs text-muted-foreground">%</span>
            <button
              type="button"
              onClick={() => remove(i)}
              disabled={disabled}
              className="h-9 w-9 rounded-full flex items-center justify-center hover:bg-secondary"
              aria-label={t('addItem.removeEntryAria', {
                label: it.name || heading,
              })}
              data-testid={`${testid}-remove-${i}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={add}
          disabled={disabled}
          className="text-xs h-8 rounded-lg"
          data-testid={`${testid}-add`}
        >
          <Plus className="h-3 w-3 me-1" /> {t('addItem.addAction')}
        </Button>
      </div>
    </div>
  );
}

export default WeightedList;
