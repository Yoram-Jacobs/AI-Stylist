import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Mic, Image as ImgIcon, Send, CloudSun, Calendar as CalIcon, Square, Sparkles, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { ScrollArea } from '@/components/ui/scroll-area';
import { WaveformAudioPlayer } from '@/components/WaveformAudioPlayer';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth';

const base64ToUrl = (b64, mime = 'audio/mpeg') => {
  if (!b64) return null;
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const blob = new Blob([bytes], { type: mime });
  return URL.createObjectURL(blob);
};

export default function Stylist() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState('');
  const [imageFile, setImageFile] = useState(null);
  const [includeCalendar, setIncludeCalendar] = useState(false);
  const [occasion, setOccasion] = useState('');
  const [calendarConnected, setCalendarConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const threadRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const h = await api.stylistHistory(20);
        const hydrated = (h.messages || []).map((m) => ({
          id: m.id, role: m.role, transcript: m.transcript, payload: m.assistant_payload,
        }));
        setMessages(hydrated);
      } catch { /* silent */ }
      try {
        const s = await api.calendarStatus();
        setCalendarConnected(!!s?.connected);
      } catch { /* silent */ }
    })();
  }, []);

  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight;
  }, [messages, busy]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      audioChunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mr.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        stream.getTracks().forEach((t) => t.stop());
        await sendTurn({ voiceBlob: blob });
      };
      mr.start();
      mediaRecorderRef.current = mr;
      setRecording(true);
    } catch {
      toast.error(t('stylist.micDenied'));
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  };

  const sendTurn = async ({ voiceBlob = null } = {}) => {
    if (busy) return;
    const body = new FormData();
    if (text.trim()) body.append('text', text.trim());
    if (voiceBlob) body.append('voice_audio', voiceBlob, 'voice.webm');
    if (imageFile) body.append('image', imageFile);
    body.append('language', user?.preferred_language || 'en');
    body.append('voice_id', user?.preferred_voice_id || 'aura-2-thalia-en');
    if (includeCalendar) {
      body.append('include_calendar', 'true');
      if (occasion) body.append('occasion', occasion);
    }
    // optimistic user bubble
    const optimistic = {
      id: `tmp-${Date.now()}`,
      role: 'user',
      transcript: voiceBlob ? t('stylist.voiceNote') : text,
      imagePreview: imageFile ? URL.createObjectURL(imageFile) : null,
    };
    setMessages((m) => [...m, optimistic]);
    setText(''); setImageFile(null);
    setBusy(true);
    try {
      const res = await api.stylist(body);
      const advice = res.advice;
      const audioUrl = base64ToUrl(advice.tts_audio_base64);
      setMessages((m) => [
        ...m,
        { id: `a-${Date.now()}`, role: 'assistant',
          transcript: advice.reasoning_summary, payload: advice, audioUrl },
      ]);
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('stylist.errorAdvice'));
    } finally { setBusy(false); }
  };

  return (
    <div className="container-px max-w-3xl mx-auto pt-4 md:pt-8 flex flex-col h-[calc(100dvh-180px)] md:h-[calc(100dvh-140px)]">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="caps-label text-muted-foreground">{t('stylist.label')}</div>
          <h1 className="font-display text-2xl md:text-3xl">{t('stylist.hero')}</h1>
        </div>
        <div className="hidden md:flex items-center gap-2">
          <Badge variant="outline" className="caps-label rounded-full bg-card"><CloudSun className="h-3 w-3 me-1" /> {t('stylist.weatherAware')}</Badge>
        </div>
      </div>

      <Card className="flex-1 rounded-[calc(var(--radius)+6px)] shadow-editorial overflow-hidden flex flex-col">
        <ScrollArea className="flex-1" data-testid="stylist-chat-thread">
          <div ref={threadRef} className="p-4 md:p-6 space-y-4">
            {messages.length === 0 && !busy && (
              <div className="text-center py-10">
                <Sparkles className="h-10 w-10 mx-auto mb-3 text-[hsl(var(--accent))]" />
                <p className="font-display text-xl">{t('stylist.askAnything')}</p>
                <p className="text-sm text-muted-foreground mt-2 max-w-sm mx-auto">{t('stylist.askAnythingSub')}</p>
              </div>
            )}
            <AnimatePresence initial={false}>
              {messages.map((m) => (
                <motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                  className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}
                  data-testid={`chat-message-${m.role}`}>
                  <div className={`max-w-[85%] rounded-2xl border px-4 py-3 ${m.role === 'user' ? 'bg-[hsl(var(--accent))]/10 border-[hsl(var(--accent))]/30' : 'bg-card border-border'}`}>
                    {m.imagePreview && (
                      <img src={m.imagePreview} alt="attachment"
                        className="rounded-lg mb-2 max-h-48 object-cover" />
                    )}
                    {m.transcript && <p className="text-sm whitespace-pre-wrap">{m.transcript}</p>}
                    {m.role === 'assistant' && m.payload && (
                      <div className="mt-3 space-y-3">
                        {(m.payload.outfit_recommendations || []).map((rec, i) => (
                          <div key={i} className="rounded-xl bg-secondary/60 border border-border p-3">
                            <div className="caps-label text-[hsl(var(--accent))]">{t('stylist.outfitN', { n: i + 1 })}</div>
                            <div className="font-display text-base mt-1">{rec.name}</div>
                            <ul className="text-xs text-muted-foreground list-disc pl-5 mt-2 space-y-0.5">
                              {(rec.items || []).map((it, j) => <li key={j}>{it.description || it.role}</li>)}
                            </ul>
                            {rec.why && <p className="text-xs mt-2 italic">{rec.why}</p>}
                          </div>
                        ))}
                        {m.payload.do_dont?.length > 0 && (
                          <div className="text-xs text-muted-foreground">
                            <div className="caps-label mb-1">{t('stylist.doDont')}</div>
                            <ul className="list-disc pl-5 space-y-0.5">
                              {m.payload.do_dont.map((d, k) => <li key={k}>{d}</li>)}
                            </ul>
                          </div>
                        )}
                        {m.payload.weather_summary && (
                          <div className="caps-label text-muted-foreground">{t('stylist.contextLabel')}: {m.payload.weather_summary}{m.payload.calendar_summary ? ` · ${m.payload.calendar_summary}` : ''}</div>
                        )}
                        {m.audioUrl && <WaveformAudioPlayer src={m.audioUrl} />}
                      </div>
                    )}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
            {busy && (
              <div className="flex justify-start" data-testid="stylist-thinking">
                <div className="max-w-[85%] rounded-2xl border border-border bg-card p-4">
                  <div className="caps-label text-muted-foreground mb-2">{t('stylist.thinking')}</div>
                  <div className="space-y-2">
                    <div className="h-3 rounded shimmer w-3/4" />
                    <div className="h-3 rounded shimmer w-1/2" />
                    <div className="h-3 rounded shimmer w-5/6" />
                  </div>
                  <p className="text-xs text-muted-foreground mt-3">{t('stylist.thinkingSub')}</p>
                </div>
              </div>
            )}
          </div>
        </ScrollArea>

        <div className="border-t border-border p-3 md:p-4 space-y-3 bg-background">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <Switch checked={includeCalendar} onCheckedChange={setIncludeCalendar} id="inc-cal" data-testid="stylist-include-calendar-switch" />
              <label htmlFor="inc-cal" className="text-xs text-muted-foreground inline-flex items-center gap-1">
                <CalIcon className="h-3.5 w-3.5" /> {t('stylist.includeCalendar')}
              </label>
              {includeCalendar && calendarConnected && (
                <Badge
                  variant="outline"
                  className="bg-emerald-50 text-emerald-800 border-emerald-200 text-[10px] py-0 h-5"
                  data-testid="stylist-calendar-live-badge"
                >
                  {t('stylist.liveCalendar')}
                </Badge>
              )}
            </div>
            {includeCalendar && !calendarConnected && (
              <input value={occasion} onChange={(e) => setOccasion(e.target.value)}
                placeholder={t('stylist.occasionPlaceholder')}
                className="text-xs bg-secondary border border-border rounded-lg px-2 py-1"
                data-testid="stylist-occasion-input" />
            )}
            {imageFile && (
              <div className="flex items-center gap-2 rounded-full border border-border bg-card px-2 py-1 text-xs" data-testid="stylist-attached-image">
                <img src={URL.createObjectURL(imageFile)} alt="" className="h-6 w-6 rounded object-cover" />
                <span className="truncate max-w-[140px]">{imageFile.name}</span>
                <button onClick={() => setImageFile(null)} aria-label={t('stylist.removeImage')} data-testid="stylist-remove-image"><X className="h-3.5 w-3.5" /></button>
              </div>
            )}
          </div>
          <div className="flex items-end gap-2">
            <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={2}
              placeholder={t('stylist.composerPlaceholder')} className="rounded-xl resize-none"
              data-testid="stylist-composer-textarea" />
            <label className="inline-flex cursor-pointer" aria-label={t('stylist.attachPhoto')} data-testid="stylist-composer-attach-button">
              <input type="file" accept="image/*" className="hidden"
                onChange={(e) => setImageFile(e.target.files?.[0] || null)} />
              <span className="inline-flex items-center justify-center h-11 w-11 rounded-xl border border-border bg-card hover:bg-secondary">
                <ImgIcon className="h-5 w-5" />
              </span>
            </label>
            {recording ? (
              <Button size="icon" variant="destructive" onClick={stopRecording} className="h-11 w-11 rounded-xl" data-testid="stylist-composer-mic-button">
                <Square className="h-5 w-5" />
              </Button>
            ) : (
              <Button size="icon" variant="secondary" onClick={startRecording} className="h-11 w-11 rounded-xl" data-testid="stylist-composer-mic-button" aria-label={t('stylist.recordVoice')}>
                <Mic className="h-5 w-5" />
              </Button>
            )}
            <Button onClick={() => sendTurn({})} disabled={busy || (!text.trim() && !imageFile)} className="h-11 rounded-xl" data-testid="stylist-composer-send-button">
              <Send className="h-5 w-5 mr-0 md:me-2" /><span className="hidden md:inline">{t('stylist.send')}</span>
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
