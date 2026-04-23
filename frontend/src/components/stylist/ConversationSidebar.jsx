import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { MessageSquare, Plus, Trash2, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

/**
 * Group sessions into Today / Yesterday / Earlier buckets based on
 * `last_active_at` (ISO string). Order within each bucket preserves the
 * input order (already newest-first).
 */
function groupSessions(sessions) {
  const out = { today: [], yesterday: [], earlier: [] };
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday.getTime() - 86400 * 1000);
  for (const s of sessions) {
    const raw = s.last_active_at || s.updated_at || s.created_at;
    const ts = raw ? new Date(raw) : null;
    if (!ts || Number.isNaN(ts.getTime())) {
      out.earlier.push(s);
      continue;
    }
    if (ts >= startOfToday) out.today.push(s);
    else if (ts >= startOfYesterday) out.yesterday.push(s);
    else out.earlier.push(s);
  }
  return out;
}

function SessionRow({ session, isActive, onSelect, onDelete, t }) {
  const title =
    (session.title && session.title.trim()) || t('stylist.untitledConversation');
  const snippet = (session.snippet || '').trim();
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        'group relative rounded-xl border px-3 py-2 cursor-pointer transition-colors',
        isActive
          ? 'bg-[hsl(var(--accent))]/10 border-[hsl(var(--accent))]/40'
          : 'bg-card border-border hover:bg-secondary',
      )}
      onClick={() => onSelect(session.id)}
      data-testid={`stylist-session-row-${session.id}`}
    >
      <div className="flex items-start gap-2 min-w-0">
        <MessageSquare className="h-3.5 w-3.5 mt-1 shrink-0 opacity-70" />
        <div className="flex-1 min-w-0">
          <div
            className={cn(
              'text-sm font-medium truncate',
              isActive ? 'text-foreground' : 'text-foreground/90',
            )}
          >
            {title}
          </div>
          {snippet ? (
            <div className="text-[11px] text-muted-foreground truncate mt-0.5">
              {snippet}
            </div>
          ) : null}
        </div>
      </div>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          if (window.confirm(t('stylist.deleteConfirm'))) onDelete(session.id);
        }}
        className={cn(
          'absolute top-1.5 right-1.5 h-7 w-7 rounded-full flex items-center justify-center',
          'opacity-0 group-hover:opacity-100 focus-visible:opacity-100',
          'hover:bg-background',
        )}
        aria-label={t('stylist.delete')}
        data-testid={`stylist-session-delete-${session.id}`}
      >
        <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
      </button>
    </motion.div>
  );
}

export function ConversationSidebar({
  sessions,
  activeId,
  onSelect,
  onNew,
  onDelete,
  loading = false,
}) {
  const { t } = useTranslation();
  const groups = useMemo(() => groupSessions(sessions || []), [sessions]);
  const empty = !loading && (sessions || []).length === 0;

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="p-3 border-b border-border">
        <Button
          onClick={onNew}
          className="w-full rounded-xl h-10"
          data-testid="stylist-new-conversation-btn"
        >
          <Plus className="h-4 w-4 me-2" /> {t('stylist.newConversation')}
        </Button>
        <div className="caps-label text-muted-foreground mt-3 ps-1">
          {t('stylist.conversations')}
        </div>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-4">
          {loading ? (
            <div
              className="flex items-center gap-2 text-xs text-muted-foreground justify-center py-6"
              data-testid="stylist-sessions-loading"
            >
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            </div>
          ) : empty ? (
            <div
              className="text-center py-8 px-3"
              data-testid="stylist-sessions-empty"
            >
              <MessageSquare className="h-7 w-7 mx-auto mb-2 text-muted-foreground opacity-60" />
              <div className="text-sm font-medium">
                {t('stylist.noConversations')}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {t('stylist.startFirst')}
              </p>
            </div>
          ) : (
            <>
              {groups.today.length > 0 && (
                <div className="space-y-1">
                  <div className="caps-label text-[10px] text-muted-foreground ps-1">
                    {t('stylist.todayLabel')}
                  </div>
                  {groups.today.map((s) => (
                    <SessionRow
                      key={s.id}
                      session={s}
                      isActive={s.id === activeId}
                      onSelect={onSelect}
                      onDelete={onDelete}
                      t={t}
                    />
                  ))}
                </div>
              )}
              {groups.yesterday.length > 0 && (
                <div className="space-y-1">
                  <div className="caps-label text-[10px] text-muted-foreground ps-1">
                    {t('stylist.yesterdayLabel')}
                  </div>
                  {groups.yesterday.map((s) => (
                    <SessionRow
                      key={s.id}
                      session={s}
                      isActive={s.id === activeId}
                      onSelect={onSelect}
                      onDelete={onDelete}
                      t={t}
                    />
                  ))}
                </div>
              )}
              {groups.earlier.length > 0 && (
                <div className="space-y-1">
                  <div className="caps-label text-[10px] text-muted-foreground ps-1">
                    {t('stylist.earlierLabel')}
                  </div>
                  {groups.earlier.map((s) => (
                    <SessionRow
                      key={s.id}
                      session={s}
                      isActive={s.id === activeId}
                      onSelect={onSelect}
                      onDelete={onDelete}
                      t={t}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
