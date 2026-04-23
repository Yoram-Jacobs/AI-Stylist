import { useEffect, useRef, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Mic,
  Image as ImgIcon,
  Send,
  CloudSun,
  Calendar as CalIcon,
  Square,
  Sparkles,
  X,
  Volume2,
  VolumeX,
  MessageSquare,
  PanelRight,
  UserRound,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { cn } from '@/lib/utils';
import { WaveformAudioPlayer } from '@/components/WaveformAudioPlayer';
import { ConversationSidebar } from '@/components/stylist/ConversationSidebar';
import { FashionScoutPanel } from '@/components/stylist/FashionScoutPanel';
import { OutfitRecommendationCard } from '@/components/stylist/OutfitRecommendationCard';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import { useAuth } from '@/lib/auth';
import { useLocation as useAppLocation } from '@/lib/location';
import {
  isSTTSupported,
  isTTSSupported,
  createRecognition,
  speak,
  cancelSpeak,
  ensureVoicesLoaded,
} from '@/lib/speech';

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
  const loc = useAppLocation();

  // Conversation state
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [messagesLoading, setMessagesLoading] = useState(false);

  // Composer state
  const [text, setText] = useState('');
  const [imageFile, setImageFile] = useState(null);
  const [includeCalendar, setIncludeCalendar] = useState(false);
  const [occasion, setOccasion] = useState('');
  const [calendarConnected, setCalendarConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [interim, setInterim] = useState('');
  const [speakingId, setSpeakingId] = useState(null);

  // Mobile drawers
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [scoutOpen, setScoutOpen] = useState(false);

  // Browser capabilities
  const sttSupportedRef = useRef(isSTTSupported());
  const ttsSupportedRef = useRef(isTTSSupported());

  // Server-side STT fallback
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const recognitionRef = useRef(null);
  const threadRef = useRef(null);

  const userLang = user?.preferred_language || 'en';

  /* ---------- Load sessions + pick active ---------- */
  const loadSessions = useCallback(async () => {
    try {
      const { sessions: rows } = await api.stylistSessions();
      setSessions(rows || []);
      return rows || [];
    } catch {
      return [];
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  const loadMessagesFor = useCallback(async (sessionId) => {
    setMessagesLoading(true);
    try {
      const h = await api.stylistHistory(sessionId, 200);
      const hydrated = (h.messages || []).map((m) => ({
        id: m.id,
        role: m.role,
        transcript: m.transcript,
        payload: m.assistant_payload,
      }));
      setMessages(hydrated);
    } catch {
      setMessages([]);
    } finally {
      setMessagesLoading(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      const rows = await loadSessions();
      if (rows.length > 0) {
        // Newest first — list_sessions returns sorted by last_active_at desc.
        const first = rows[0];
        setActiveSessionId(first.id);
        await loadMessagesFor(first.id);
      }
      try {
        const s = await api.calendarStatus();
        setCalendarConnected(!!s?.connected);
      } catch {
        /* silent */
      }
    })();
    if (ttsSupportedRef.current) {
      ensureVoicesLoaded().catch(() => {});
    }
    return () => {
      cancelSpeak();
      try {
        recognitionRef.current?.abort?.();
      } catch {
        /* ignore */
      }
    };
  }, [loadSessions, loadMessagesFor]);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages, busy]);

  /* ---------- Session actions ---------- */
  const handleSelectSession = async (id) => {
    if (id === activeSessionId) {
      setSidebarOpen(false);
      return;
    }
    setActiveSessionId(id);
    setSidebarOpen(false);
    await loadMessagesFor(id);
  };

  const handleNewConversation = async () => {
    try {
      const fresh = await api.stylistCreateSession();
      setActiveSessionId(fresh.id);
      setMessages([]);
      setText('');
      setImageFile(null);
      setSidebarOpen(false);
      // Optimistically prepend the new session to the sidebar so the user
      // sees it immediately; the real snapshot will reconcile on next load.
      setSessions((prev) => [fresh, ...(prev || [])]);
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('stylist.errorAdvice'));
    }
  };

  const handleDeleteSession = async (id) => {
    try {
      await api.stylistDeleteSession(id);
      const remaining = sessions.filter((s) => s.id !== id);
      setSessions(remaining);
      if (id === activeSessionId) {
        if (remaining.length > 0) {
          setActiveSessionId(remaining[0].id);
          await loadMessagesFor(remaining[0].id);
        } else {
          // Auto-create a fresh empty session so the composer stays usable.
          const fresh = await api.stylistCreateSession();
          setSessions([fresh]);
          setActiveSessionId(fresh.id);
          setMessages([]);
        }
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('common.error'));
    }
  };

  /* ---------- Native STT path (preferred) ---------- */
  const startNativeRecognition = () => {
    try {
      const rec = createRecognition({
        lang: userLang,
        interimResults: true,
        continuous: false,
      });
      recognitionRef.current = rec;
      setInterim('');
      setRecording(true);
      let finalText = '';
      rec.onresult = (event) => {
        let interimText = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) finalText += transcript;
          else interimText += transcript;
        }
        setInterim(interimText);
      };
      rec.onerror = () => {
        setRecording(false);
        toast.error(t('stylist.voiceError'));
      };
      rec.onend = () => {
        setRecording(false);
        setInterim('');
        if (finalText.trim()) {
          sendTurn({ overrideText: finalText.trim() });
        }
      };
      rec.start();
      return true;
    } catch {
      recognitionRef.current = null;
      return false;
    }
  };

  /* ---------- MediaRecorder fallback ---------- */
  const startMediaRecorder = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      mediaRecorderRef.current = mr;
      audioChunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data?.size) audioChunksRef.current.push(e.data);
      };
      mr.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        stream.getTracks().forEach((x) => x.stop());
        await sendTurn({ voiceBlob: blob });
      };
      mr.start();
      setRecording(true);
    } catch {
      toast.error(t('stylist.micError'));
    }
  };

  const startRecording = () => {
    if (sttSupportedRef.current && startNativeRecognition()) return;
    startMediaRecorder();
  };

  const stopRecording = () => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        /* ignore */
      }
      recognitionRef.current = null;
      return;
    }
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    setRecording(false);
  };

  /* ---------- Local TTS ---------- */
  const playLocalSpeech = async (id, txt) => {
    if (!txt) return;
    try {
      setSpeakingId(id);
      await speak(txt, { lang: userLang });
    } catch {
      /* ignore */
    } finally {
      setSpeakingId(null);
    }
  };
  const stopLocalSpeech = () => {
    cancelSpeak();
    setSpeakingId(null);
  };

  /* ---------- Compose + send turn ---------- */
  const sendTurn = async ({ voiceBlob = null, overrideText = null } = {}) => {
    if (busy) return;
    const outgoingText = (overrideText ?? text).trim();
    const body = new FormData();
    if (outgoingText) body.append('text', outgoingText);
    if (voiceBlob) body.append('voice_audio', voiceBlob, 'voice.webm');
    if (imageFile) body.append('image', imageFile);
    body.append('language', userLang);
    body.append('voice_id', user?.preferred_voice_id || 'aura-2-thalia-en');
    if (activeSessionId) body.append('session_id', activeSessionId);
    if (ttsSupportedRef.current) body.append('skip_tts', 'true');
    // Augment the turn with the device coordinates so the stylist can
    // ground weather + regional context without waiting for a background
    // call. Falls back to the user's saved home_location server-side.
    if (loc?.coords?.lat != null && loc?.coords?.lng != null) {
      body.append('lat', String(loc.coords.lat));
      body.append('lng', String(loc.coords.lng));
    }
    if (includeCalendar) {
      body.append('include_calendar', 'true');
      if (occasion) body.append('occasion', occasion);
    }

    const optimistic = {
      id: `tmp-${Date.now()}`,
      role: 'user',
      transcript: voiceBlob ? t('stylist.voiceNote') : outgoingText,
      imagePreview: imageFile ? URL.createObjectURL(imageFile) : null,
    };
    setMessages((m) => [...m, optimistic]);
    setText('');
    setImageFile(null);
    setBusy(true);
    try {
      const res = await api.stylist(body);
      const advice = res.advice;
      const audioUrl = base64ToUrl(advice.tts_audio_base64);
      const newId = `a-${Date.now()}`;
      setMessages((m) => [
        ...m,
        {
          id: newId,
          role: 'assistant',
          transcript: advice.reasoning_summary,
          payload: advice,
          audioUrl,
          spokenText: advice.spoken_reply || advice.reasoning_summary || '',
        },
      ]);
      // Update the active session meta (title + snippet + id) in the sidebar.
      if (res.session) {
        setActiveSessionId(res.session.id);
        setSessions((prev) => {
          const without = (prev || []).filter((s) => s.id !== res.session.id);
          return [res.session, ...without];
        });
      }
      if (ttsSupportedRef.current && !audioUrl) {
        const spoken = advice.spoken_reply || advice.reasoning_summary || '';
        if (spoken) playLocalSpeech(newId, spoken);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('stylist.errorAdvice'));
      // Roll back optimistic user bubble on failure so the user can retry.
      setMessages((m) => m.filter((x) => x.id !== optimistic.id));
    } finally {
      setBusy(false);
    }
  };

  /* ---------- Render helpers ---------- */
  const chatColumn = (
    <Card className="h-full flex flex-col rounded-[calc(var(--radius)+6px)] shadow-editorial overflow-hidden">
      {/* Sticky top bar */}
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 md:px-4 py-2.5 bg-background">
        <div className="flex items-center gap-2 min-w-0">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden h-9 w-9 rounded-lg border border-border bg-card flex items-center justify-center"
            aria-label={t('stylist.openConversations')}
            data-testid="stylist-open-sidebar-btn"
          >
            <MessageSquare className="h-4 w-4" />
          </button>
          <div className="min-w-0">
            <div className="caps-label text-muted-foreground truncate">
              {t('stylist.label')}
            </div>
            <h1 className="font-display text-lg md:text-xl truncate">
              {sessions.find((s) => s.id === activeSessionId)?.title ||
                t('stylist.hero')}
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Badge
            variant="outline"
            className="hidden md:inline-flex caps-label rounded-full bg-card"
          >
            <CloudSun className="h-3 w-3 me-1" /> {t('stylist.weatherAware')}
          </Badge>
          {(sttSupportedRef.current || ttsSupportedRef.current) && (
            <Badge
              variant="outline"
              className="hidden md:inline-flex caps-label rounded-full bg-card"
              data-testid="stylist-native-speech-badge"
            >
              <Mic className="h-3 w-3 me-1" /> {t('stylist.nativeSpeech')}
            </Badge>
          )}
          <button
            type="button"
            onClick={() => setScoutOpen(true)}
            className="xl:hidden h-9 w-9 rounded-lg border border-border bg-card flex items-center justify-center"
            aria-label={t('stylist.openScout')}
            data-testid="stylist-open-scout-btn"
          >
            <PanelRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      <ScrollArea className="flex-1" data-testid="stylist-chat-thread">
        <div ref={threadRef} className="p-4 md:p-6 space-y-4">
          {messages.length === 0 && !busy && !messagesLoading && (
            <div className="text-center py-10">
              <Sparkles className="h-10 w-10 mx-auto mb-3 text-[hsl(var(--accent))]" />
              <p className="font-display text-xl">{t('stylist.askAnything')}</p>
              <p className="text-sm text-muted-foreground mt-2 max-w-sm mx-auto">
                {t('stylist.askAnythingSub')}
              </p>
            </div>
          )}
          <AnimatePresence initial={false}>
            {messages.map((m) => (
              <motion.div
                key={m.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className={
                  m.role === 'user' ? 'flex justify-end' : 'flex justify-start'
                }
                data-testid={`chat-message-${m.role}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl border px-4 py-3 ${
                    m.role === 'user'
                      ? 'bg-[hsl(var(--accent))]/10 border-[hsl(var(--accent))]/30'
                      : 'bg-card border-border'
                  }`}
                >
                  {m.imagePreview && (
                    <img
                      src={m.imagePreview}
                      alt="attachment"
                      className="rounded-lg mb-2 max-h-48 object-cover"
                    />
                  )}
                  {m.transcript && (
                    <p className="text-sm whitespace-pre-wrap">{m.transcript}</p>
                  )}
                  {m.role === 'assistant' && m.payload && (
                    <div className="mt-3 space-y-3">
                      {(m.payload.outfit_recommendations || []).map((rec, i) => (
                        <OutfitRecommendationCard
                          key={i}
                          rec={rec}
                          index={i}
                          sessionId={activeSessionId}
                        />
                      ))}
                      {m.payload.do_dont?.length > 0 && (
                        <div className="text-xs text-muted-foreground">
                          <div className="caps-label mb-1">
                            {t('stylist.doDont')}
                          </div>
                          <ul className="list-disc ps-5 space-y-0.5">
                            {m.payload.do_dont.map((d, k) => (
                              <li key={k}>{d}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {m.payload.weather_summary && (
                        <div className="caps-label text-muted-foreground">
                          {t('stylist.contextLabel')}: {m.payload.weather_summary}
                          {m.payload.calendar_summary
                            ? ` · ${m.payload.calendar_summary}`
                            : ''}
                        </div>
                      )}
                      {m.audioUrl ? (
                        <WaveformAudioPlayer src={m.audioUrl} />
                      ) : ttsSupportedRef.current && m.spokenText ? (
                        <div className="flex items-center gap-2">
                          {speakingId === m.id ? (
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={stopLocalSpeech}
                              className="h-8 rounded-full"
                              data-testid={`stylist-stop-speak-${m.id}`}
                            >
                              <VolumeX className="h-3.5 w-3.5 me-1" />
                              {t('stylist.stopSpeaking')}
                            </Button>
                          ) : (
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => playLocalSpeech(m.id, m.spokenText)}
                              className="h-8 rounded-full"
                              data-testid={`stylist-play-speak-${m.id}`}
                            >
                              <Volume2 className="h-3.5 w-3.5 me-1" />
                              {t('stylist.playReply')}
                            </Button>
                          )}
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
          {busy && (
            <div className="flex justify-start" data-testid="stylist-thinking">
              <div className="max-w-[85%] rounded-2xl border border-border bg-card p-4">
                <div className="caps-label text-muted-foreground mb-2">
                  {t('stylist.thinking')}
                </div>
                <div className="space-y-2">
                  <div className="h-3 rounded shimmer w-3/4" />
                  <div className="h-3 rounded shimmer w-1/2" />
                  <div className="h-3 rounded shimmer w-5/6" />
                </div>
                <p className="text-xs text-muted-foreground mt-3">
                  {t('stylist.thinkingSub')}
                </p>
              </div>
            </div>
          )}
          {recording && interim && (
            <div
              className="flex justify-end"
              data-testid="stylist-interim-transcript"
            >
              <div className="max-w-[85%] rounded-2xl border border-dashed border-[hsl(var(--accent))]/40 bg-[hsl(var(--accent))]/5 px-4 py-3">
                <div className="caps-label text-[hsl(var(--accent))] mb-1">
                  {t('stylist.listening')}
                </div>
                <p className="text-sm whitespace-pre-wrap italic">{interim}</p>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      <div className="border-t border-border p-3 md:p-4 space-y-3 bg-background">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Switch
              checked={includeCalendar}
              onCheckedChange={setIncludeCalendar}
              id="inc-cal"
              data-testid="stylist-include-calendar-switch"
            />
            <label
              htmlFor="inc-cal"
              className="text-xs text-muted-foreground inline-flex items-center gap-1"
            >
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
            <input
              value={occasion}
              onChange={(e) => setOccasion(e.target.value)}
              placeholder={t('stylist.occasionPlaceholder')}
              className="text-xs bg-secondary border border-border rounded-lg px-2 py-1"
              data-testid="stylist-occasion-input"
            />
          )}
          {imageFile && (
            <div
              className="flex items-center gap-2 rounded-full border border-border bg-card px-2 py-1 text-xs"
              data-testid="stylist-attached-image"
            >
              <img
                src={URL.createObjectURL(imageFile)}
                alt=""
                className="h-6 w-6 rounded object-cover"
              />
              <span className="truncate max-w-[140px]">{imageFile.name}</span>
              <button
                onClick={() => setImageFile(null)}
                aria-label={t('stylist.removeImage')}
                data-testid="stylist-remove-image"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          <div className="ms-auto">
            <button
              type="button"
              disabled
              title={
                loc?.coords
                  ? t('stylist.askProfessionalLocal')
                  : t('stylist.askProfessionalSoon')
              }
              className={cn(
                'inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs',
                'border border-dashed border-[hsl(var(--accent))]/40 text-[hsl(var(--accent))]',
                'opacity-70 cursor-not-allowed',
              )}
              data-testid="stylist-ask-professional-btn"
            >
              <UserRound className="h-3.5 w-3.5" />
              {t('stylist.askProfessional')}
              <Badge
                variant="outline"
                className="ms-1 text-[9px] py-0 h-4 px-1 rounded-sm bg-card"
              >
                {t('common.comingSoon')}
              </Badge>
            </button>
          </div>
        </div>
        <div className="flex items-end gap-2">
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={2}
            placeholder={t('stylist.composerPlaceholder')}
            className="rounded-xl resize-none"
            data-testid="stylist-composer-textarea"
          />
          <label
            className="inline-flex cursor-pointer"
            aria-label={t('stylist.attachPhoto')}
            data-testid="stylist-composer-attach-button"
          >
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => setImageFile(e.target.files?.[0] || null)}
            />
            <span className="inline-flex items-center justify-center h-11 w-11 rounded-xl border border-border bg-card hover:bg-secondary">
              <ImgIcon className="h-5 w-5" />
            </span>
          </label>
          {recording ? (
            <Button
              size="icon"
              variant="destructive"
              onClick={stopRecording}
              className="h-11 w-11 rounded-xl"
              aria-label={t('stylist.tapToStop')}
              data-testid="stylist-composer-mic-button"
            >
              <Square className="h-5 w-5" />
            </Button>
          ) : (
            <Button
              size="icon"
              variant="secondary"
              onClick={startRecording}
              className="h-11 w-11 rounded-xl"
              data-testid="stylist-composer-mic-button"
              aria-label={t('stylist.recordVoice')}
            >
              <Mic className="h-5 w-5" />
            </Button>
          )}
          <Button
            onClick={() => sendTurn({})}
            disabled={busy || (!text.trim() && !imageFile)}
            className="h-11 rounded-xl"
            data-testid="stylist-composer-send-button"
          >
            <Send className="h-5 w-5 mr-0 md:me-2" />
            <span className="hidden md:inline">{t('stylist.send')}</span>
          </Button>
        </div>
      </div>
    </Card>
  );

  return (
    <div className="container-px max-w-[1600px] mx-auto pt-4 md:pt-6">
      <div className="grid grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[280px_minmax(0,1fr)_340px] gap-4 h-[calc(100dvh-180px)] md:h-[calc(100dvh-140px)]">
        {/* Left rail — desktop only */}
        <aside
          className="hidden lg:flex rounded-[calc(var(--radius)+6px)] bg-card border border-border overflow-hidden"
          data-testid="stylist-conversation-sidebar"
        >
          <ConversationSidebar
            sessions={sessions}
            activeId={activeSessionId}
            onSelect={handleSelectSession}
            onNew={handleNewConversation}
            onDelete={handleDeleteSession}
            loading={sessionsLoading}
          />
        </aside>

        {/* Center — chat */}
        <main className="min-w-0 flex flex-col">{chatColumn}</main>

        {/* Right rail — desktop only */}
        <aside
          className="hidden xl:flex rounded-[calc(var(--radius)+6px)] bg-card border border-border overflow-hidden"
          data-testid="stylist-fashion-scout"
        >
          <FashionScoutPanel />
        </aside>
      </div>

      {/* Mobile drawer — conversations */}
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="p-0 w-[320px] sm:w-[360px]">
          <SheetHeader className="sr-only">
            <SheetTitle>{t('stylist.conversations')}</SheetTitle>
          </SheetHeader>
          <ConversationSidebar
            sessions={sessions}
            activeId={activeSessionId}
            onSelect={handleSelectSession}
            onNew={handleNewConversation}
            onDelete={handleDeleteSession}
            loading={sessionsLoading}
          />
        </SheetContent>
      </Sheet>

      {/* Mobile/tablet drawer — fashion scout */}
      <Sheet open={scoutOpen} onOpenChange={setScoutOpen}>
        <SheetContent side="right" className="p-0 w-[340px] sm:w-[380px]">
          <SheetHeader className="sr-only">
            <SheetTitle>{t('stylist.fashionScout')}</SheetTitle>
          </SheetHeader>
          <FashionScoutPanel />
        </SheetContent>
      </Sheet>
    </div>
  );
}
