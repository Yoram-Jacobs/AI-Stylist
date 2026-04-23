import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { labelForSource } from '@/lib/taxonomy';

const STYLES = {
  Private: 'bg-secondary text-foreground border border-border',
  Shared:
    'bg-[hsl(var(--accent))]/10 text-[hsl(var(--accent))] border border-[hsl(var(--accent))]/30',
  Retail:
    'bg-[hsl(var(--persimmon))]/10 text-[hsl(var(--persimmon))] border border-[hsl(var(--persimmon))]/30',
};

export const SourceTagBadge = ({ source = 'Private', className }) => {
  const { t } = useTranslation();
  return (
    <Badge
      data-testid="source-tag-badge"
      variant="outline"
      className={cn('rounded-full caps-label px-2.5 py-1', STYLES[source] || STYLES.Private, className)}
    >
      {labelForSource(source, t)}
    </Badge>
  );
};
