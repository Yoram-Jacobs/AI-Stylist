// Site-specific selector pack. Each function returns the chart node,
// or null if not found on this page. We keep them deliberately small
// — if a selector misses, the generic adapter takes over.
import generic from './generic.js';

function first(_doc, ...sels) { for (const s of sels) { const el = _doc.querySelector(s); if (el) return el; } return null; }

export const zara      = (d) => first(d, '[class*=size-info]', '[class*=size-table]', '[data-qa-action="size-list"] table') || generic.detectChart(d);
export const asos      = (d) => first(d, '#sizing-help-modal table', '[data-testid="size-guide"] table', '[class*=sizeguide] table') || generic.detectChart(d);
export const shein     = (d) => first(d, '.size-info-table', '.size-guide-table', '[class*=sizeGuide] table') || generic.detectChart(d);
export const hm        = (d) => first(d, '[data-elid="size-guide"] table', '[class*=size-guide] table', '#sizeGuide table') || generic.detectChart(d);
export const amazon    = (d) => first(d, '#sizeChartContent', '#prodDetails table', '[id*=size-chart]') || generic.detectChart(d);
export const aliexpress = (d) => first(d, '[class*=size-guide]', '[class*=SizeGuide] table', '[data-pl="size-guide"] table') || generic.detectChart(d);

export function getAdapter(host) {
  const h = (host || '').toLowerCase();
  if (h.includes('zara.com'))         return { name: 'zara',       detectChart: zara };
  if (h.includes('asos.com'))         return { name: 'asos',       detectChart: asos };
  if (h.includes('shein.com'))        return { name: 'shein',      detectChart: shein };
  if (h.includes('hm.com'))           return { name: 'hm',         detectChart: hm };
  if (h.includes('amazon.'))          return { name: 'amazon',     detectChart: amazon };
  if (h.includes('aliexpress.'))      return { name: 'aliexpress', detectChart: aliexpress };
  return { name: 'generic', detectChart: generic.detectChart };
}
