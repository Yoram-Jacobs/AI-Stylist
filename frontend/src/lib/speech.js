/**
 * System-native Speech helpers (Phase M).
 *
 * Wraps the browser Web Speech API:
 *  - Speech-to-Text  ->  window.SpeechRecognition / window.webkitSpeechRecognition
 *  - Text-to-Speech  ->  window.speechSynthesis
 *
 * When unsupported (e.g. Firefox desktop), `isSTTSupported()` / `isTTSSupported()`
 * return `false` and callers should fall back to the existing server-side
 * Groq Whisper / Deepgram Aura pipeline.
 */

/* ---------- BCP-47 locale mapping ---------- */
// Our app stores short locale codes (`en`, `he`, `zh`, ...); the Web Speech API
// expects BCP-47 tags (`en-US`, `he-IL`, `zh-CN`, ...).
const BCP47 = {
  en: 'en-US',
  he: 'he-IL',
  ar: 'ar-SA',
  es: 'es-ES',
  fr: 'fr-FR',
  de: 'de-DE',
  it: 'it-IT',
  pt: 'pt-PT',
  ru: 'ru-RU',
  zh: 'zh-CN',
  ja: 'ja-JP',
  hi: 'hi-IN',
};

export function toBcp47(lang) {
  if (!lang) return 'en-US';
  if (lang.includes('-')) return lang; // already BCP-47
  return BCP47[lang.toLowerCase()] || 'en-US';
}

/* ---------- Feature detection ---------- */
export function getSpeechRecognitionCtor() {
  if (typeof window === 'undefined') return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

export function isSTTSupported() {
  return !!getSpeechRecognitionCtor();
}

export function isTTSSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

/* ---------- TTS voice loading ---------- */
// Chrome/Safari load voices asynchronously; ensure they're primed before first use.
let _voicesPromise = null;
export function ensureVoicesLoaded() {
  if (!isTTSSupported()) return Promise.resolve([]);
  if (_voicesPromise) return _voicesPromise;
  _voicesPromise = new Promise((resolve) => {
    const synth = window.speechSynthesis;
    const existing = synth.getVoices();
    if (existing && existing.length) return resolve(existing);
    const handler = () => {
      synth.removeEventListener('voiceschanged', handler);
      resolve(synth.getVoices());
    };
    synth.addEventListener('voiceschanged', handler);
    // Safety timeout — some browsers never fire the event
    setTimeout(() => {
      synth.removeEventListener('voiceschanged', handler);
      resolve(synth.getVoices());
    }, 1500);
  });
  return _voicesPromise;
}

function pickVoice(voices, bcp47) {
  if (!voices || !voices.length) return null;
  const lower = bcp47.toLowerCase();
  const langPrefix = lower.split('-')[0];
  // 1) exact match (e.g. "he-IL")
  let v = voices.find((vv) => vv.lang?.toLowerCase() === lower);
  if (v) return v;
  // 2) same language family (e.g. any "he-*")
  v = voices.find((vv) => vv.lang?.toLowerCase().startsWith(`${langPrefix}-`));
  if (v) return v;
  // 3) bare language match
  v = voices.find((vv) => vv.lang?.toLowerCase() === langPrefix);
  if (v) return v;
  return null;
}

/* ---------- TTS: speak / cancel ---------- */
export async function speak(text, lang = 'en', { onStart, onEnd, onError } = {}) {
  if (!isTTSSupported() || !text) {
    onEnd?.();
    return null;
  }
  const synth = window.speechSynthesis;
  // Cancel anything currently speaking (avoids queued playback surprises).
  try { synth.cancel(); } catch { /* ignore */ }
  const voices = await ensureVoicesLoaded();
  const bcp = toBcp47(lang);
  const voice = pickVoice(voices, bcp);
  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = bcp;
  if (voice) utter.voice = voice;
  utter.rate = 1.0;
  utter.pitch = 1.0;
  utter.volume = 1.0;
  if (onStart) utter.onstart = onStart;
  utter.onend = () => { onEnd?.(); };
  utter.onerror = (e) => { onError?.(e); onEnd?.(); };
  try {
    synth.speak(utter);
  } catch (e) {
    onError?.(e);
    onEnd?.();
  }
  return utter;
}

export function cancelSpeak() {
  if (!isTTSSupported()) return;
  try { window.speechSynthesis.cancel(); } catch { /* ignore */ }
}

/* ---------- STT: create recognition session ----------
 *
 * Returns an object with `start()` and `stop()` methods. The caller supplies
 * callbacks:
 *   onInterim(text)  -> live partial transcript (can be fired many times)
 *   onFinal(text)    -> fires exactly once when recognition ends cleanly
 *   onError(err)     -> fires on recognition errors (permission denied, etc.)
 *   onEnd()          -> always fires when the session stops (after onFinal)
 */
export function createRecognition({
  lang = 'en',
  onInterim,
  onFinal,
  onError,
  onEnd,
} = {}) {
  const Ctor = getSpeechRecognitionCtor();
  if (!Ctor) return null;
  const rec = new Ctor();
  rec.lang = toBcp47(lang);
  rec.interimResults = true;
  rec.continuous = false;
  rec.maxAlternatives = 1;

  let finalText = '';
  let interimText = '';

  rec.onresult = (event) => {
    interimText = '';
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const r = event.results[i];
      const chunk = r[0]?.transcript || '';
      if (r.isFinal) {
        finalText += (finalText ? ' ' : '') + chunk.trim();
      } else {
        interimText += chunk;
      }
    }
    onInterim?.((finalText ? `${finalText} ` : '') + interimText);
  };

  rec.onerror = (event) => {
    onError?.(event);
  };

  rec.onend = () => {
    const combined = (finalText || interimText || '').trim();
    if (combined) onFinal?.(combined);
    onEnd?.();
  };

  return {
    start: () => {
      finalText = '';
      interimText = '';
      try {
        rec.start();
      } catch (e) {
        onError?.(e);
        onEnd?.();
      }
    },
    stop: () => {
      try { rec.stop(); } catch { /* ignore */ }
    },
    abort: () => {
      try { rec.abort(); } catch { /* ignore */ }
    },
  };
}
