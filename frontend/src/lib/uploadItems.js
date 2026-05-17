/**
 * uploadItems.js — SEALED Upload-Items pipeline (Phase U1, May 2026).
 *
 * ──────────────────────────────────────────────────────────────────
 *  THIS MODULE IS A CLOSED SYSTEM. DO NOT REINVENT IT.
 * ──────────────────────────────────────────────────────────────────
 *
 *  Every add-item workflow in DressApp MUST flow through this module:
 *    • single-photo upload          (file picker, 1 file)
 *    • multi-photo upload           (file picker, 2..N files)
 *    • camera capture               (mobile rear camera, 1 file)
 *    • drag-and-drop                (any count)
 *    • DPP QR scan                  (1 fully-hydrated draft)
 *    • programmatic callers         (e.g. Stylist "save outfit
 *                                    suggestion") via `start()`
 *
 *  Drift between pipelines is the #1 source of regressions in this
 *  area (M20.5/M20.5.1 cost a full session). Treat the public API
 *  below as frozen. New behavior goes inside, not in parallel.
 *
 *  ──────────────────────────────────────────────────────────────────
 *   Provider independence (Gemma ↔ Gemini)
 *  ──────────────────────────────────────────────────────────────────
 *  This module talks to the backend at exactly ONE endpoint:
 *    POST /api/v1/closet/analyze   (via `api.analyzeItemImage`)
 *
 *  The backend chooses between self-hosted Gemma 4 E2B and Gemini
 *  via the runtime Mongo override (`backend/app/services/
 *  eyes_override.py`, doc `dressapp_prod.config._id=eyes_provider`,
 *  value `"gemma" | "gemini"`, 5 s cache).
 *
 *  *** This module MUST NOT reference any provider, model name,
 *  *** API key, or HF token. Flipping the provider is a backend-only
 *  *** operation and must require ZERO frontend change.
 *
 *  ──────────────────────────────────────────────────────────────────
 *   Public API (frozen — sealed contract)
 *  ──────────────────────────────────────────────────────────────────
 *
 *    uploadItems.start(files, opts) -> void | Promise<{saved, failed}>
 *      The canonical entry point. Routes through:
 *        fingerprinting -> pre-flight duplicate detection ->
 *        analyze (NDJSON stream, multi-garment split) -> per-card
 *        review state -> optimistic save -> background polish
 *        registration.
 *
 *      `opts`:
 *        - mode: 'fire-and-forget' (default) | 'awaitable'
 *            'awaitable' returns a Promise that resolves with
 *            `{saved: [item, ...], failed: [{filename, error}, ...]}`
 *            once the batch fully settles (analyses complete + saves
 *            complete + per-item polish doesn't block resolution).
 *        - autoSave: boolean (default false on /add, true for
 *            programmatic callers). When true, saveAll fires
 *            automatically once every card reaches a terminal state.
 *            When false the user must press the Save button.
 *        - autoResolveDuplicates: 'prompt' | 'skip' | 'add-all'
 *            (default 'prompt') Determines what to do when the
 *            pre-flight finds matches in the closet. `prompt`
 *            requires a host page to mount the dialog and call
 *            `resolvePreflight()`. `skip`/`add-all` are
 *            non-interactive — used by programmatic callers.
 *        - user: the auth user object, used to fall back to stored
 *            size preferences when the analyzer doesn't return a
 *            size. Optional.
 *
 *    uploadItems.subscribe(fn) -> () => void
 *      Plain state subscription. `fn()` fires after every state
 *      mutation. Use `getSnapshot()` to read.
 *
 *    uploadItems.getSnapshot() -> StateSnapshot
 *
 *    uploadItems.onBatchSettled(fn) -> () => void
 *      Fires once per batch after every card has reached a terminal
 *      state (saved / failed / error). Used by `AddItem.jsx` to
 *      navigate to `/closet` and by awaitable callers internally.
 *
 *    uploadItems.removeCard(id)
 *    uploadItems.retryCard(id, opts?)
 *    uploadItems.updateField(id, patch)        // patch into card.fields
 *    uploadItems.patchCard(id, patch)          // patch top-level card props
 *    uploadItems.saveAll(opts?)                // manual fire
 *    uploadItems.hydrateFromDpp(res, user?)    // inject a ready DPP draft
 *    uploadItems.resolvePreflight(decisions, user?)
 *    uploadItems.acceptDuplicate(cardId)
 *    uploadItems.discardDuplicate(cardId)
 *    uploadItems.clearPreflight()
 *    uploadItems.reset()                       // test hook only
 *
 *    useUploadItems(opts?) -> { ...snapshot, ...bound mutators }
 *      Reactive React wrapper. Automatically forwards `user` from
 *      `useAuth()` to the mutators that need it (start, saveAll,
 *      hydrateFromDpp, resolvePreflight, retryCard).
 *
 *  ──────────────────────────────────────────────────────────────────
 *   Card lifecycle (single source of truth)
 *  ──────────────────────────────────────────────────────────────────
 *
 *    user drops files -> start()
 *      -> fingerprint each file (sha256 + aHash + colour-sig)
 *      -> findDuplicatesInCloset() against closetStore snapshot
 *      -> [if matches && autoResolveDuplicates==='prompt']
 *           expose `preflight` state and WAIT until host page calls
 *           resolvePreflight()
 *         [if matches && autoResolveDuplicates==='skip']
 *           filter dupes out
 *         [if matches && autoResolveDuplicates==='add-all']
 *           keep all, stamp isDuplicate=true on the matched ones
 *      -> drafts built (status='scanning')
 *      -> per-draft analyzeCard() fires concurrently (NDJSON stream
 *           via api.analyzeItemImage). Stream emits:
 *             detect frame -> split draft into N placeholders
 *             item frames  -> hydrate each placeholder (status→ready)
 *             item_skip    -> remove placeholder
 *             error frame  -> draft.status='error'
 *      -> when every card is terminal AND autoSave OR user clicks
 *         Save -> saveAll() runs optimistic-first POST /closet for
 *         every card. closetStore receives ghost docs immediately.
 *      -> settle() awaits the createItem Promise.allSettled,
 *         reconciles ghosts, registers polish items with workStore,
 *         records failures on closetStore.
 *      -> onBatchSettled(...) fires.
 *
 *  Drift bait checklist (do not reintroduce):
 *    1. NO parallel `handleBatchBackground` for >5 photos. The
 *       count threshold is GONE. Same code for 1..N files.
 *    2. NO `setTimeout(0, saveAll)` race. Use `pendingAutoSave`
 *       state + auto-drain effect.
 *    3. Placeholder cards MUST inherit source fingerprints
 *       (sourceSha256/sourcePhash/sourceColorSig/sourceFilename/
 *       sourceSizeBytes/isDuplicate) from their parent draft.
 *       See M20.5.2 root-cause writeup in plan.md.
 *    4. NEVER hardcode model / provider / token / endpoint other
 *       than `/closet/analyze` and `/closet`. Backend `eyes_override`
 *       is the switch.
 */

import { useEffect, useSyncExternalStore } from 'react';
import { toast } from 'sonner';
import i18n from 'i18next';

import { api } from '@/lib/api';
import { sha256File, aHashFile, colorSignatureFile } from '@/lib/utils';
import { findDuplicatesInCloset } from '@/lib/duplicateDetection';
import { closetStore } from '@/lib/closetStore';
import { workStore } from '@/lib/workStore';
import { deriveSizeFromPreferences } from '@/lib/size_preferences';

/* ============================================================
 *  Internal constants — never exported.
 * ============================================================ */

const _INTENT_OWN = 'own';
const _SOURCE_PRIVATE = 'Private';
const _SOURCE_SHARED = 'Shared';

/** Translation helper — pulls from the live `i18next` instance so
 * strings come back in whatever locale the user is reading the app
 * in. Defensive fallback returns the key when i18n isn't ready. */
const _t = (key, opts) => {
  try {
    return i18n.t(key, opts);
  } catch {
    return (opts && opts.defaultValue) || key;
  }
};

/** Convert a File to bare base64 (strips the data: prefix). */
const _fileToBase64 = (file) =>
  new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onerror = reject;
    r.onload = () => {
      const s = String(r.result || '');
      const comma = s.indexOf(',');
      resolve(comma >= 0 ? s.slice(comma + 1) : s);
    };
    r.readAsDataURL(file);
  });

/** Blank form object — the "fields" half of a card. Mirrors
 * `ClosetItem` fields the user edits on /add. */
const _blankFields = () => ({
  name: '', title: '', caption: '',
  category: '', sub_category: '', item_type: '', brand: '',
  gender: '', dress_code: '', season: [], tradition: '',
  colors: [], fabric_materials: [], pattern: '',
  state: '', condition: '', quality: '',
  size: '', price_cents: 0, currency: 'USD',
  marketplace_intent: _INTENT_OWN,
  repair_advice: '',
  tags: [],
});

/** Coerce analyze payload into a plain, editable form dict.
 *
 * When `user` is provided and the analyser didn't return a usable
 * `size` (couldn't read a tag, blank crop, …), we fall back to
 * the user's stored body-measurement preference for the relevant
 * garment category — Top→shirt_size, Bottom→pants_size, etc.
 */
const _hydrate = (a, user) => {
  const out = {
    ..._blankFields(),
    ...Object.fromEntries(
      Object.entries(a || {}).filter(([k]) => k in _blankFields()),
    ),
  };
  if (user && (!out.size || String(out.size).trim() === '')) {
    const pref = deriveSizeFromPreferences(user, out);
    if (pref) out.size = pref;
  }
  return out;
};

/* ============================================================
 *  Singleton state — module scope, survives navigation.
 * ============================================================ */

let _state = {
  /** Array of card objects.
   *
   * card = {
   *   id, file, mime, previewUrl, base64,
   *   status: 'scanning' | 'ready' | 'error' | 'saving' | 'saved',
   *   progress: 0..100,
   *   fields: blankFields(),
   *   error: string | null,
   *   label: string | null,        // detected item type
   *   dppData?: object,             // when source === 'dpp'
   *   source?: 'dpp' | undefined,
   *   // source-photo fingerprints (Phase Z2)
   *   sourceSha256, sourcePhash, sourceColorSig,
   *   sourceFilename, sourceSizeBytes, isDuplicate,
   *   // analyzer-supplied flags
   *   deferMatte, needsReconstruction, reconstructionReasons,
   *   fromOnePass, reconstructionAdvised,
   *   // duplicate handling
   *   potentialDuplicate, duplicateConfirmed,
   *   // reconstruction (Nano Banana — currently disabled)
   *   reconstructedUrl, reconstructedB64, reconstructionMeta,
   *   useReconstructed, originalCropUrl,
   *   // stream bookkeeping
   *   _streamSlot, analyzeError,
   *   _batchId,                     // links card to its start() batch
   * }
   */
  cards: [],
  /** True while saveAll is in flight. */
  saving: false,
  /** True when saveAll was triggered while some cards were still
   * scanning; the drain effect re-fires saveAll when all settle. */
  pendingAutoSave: false,
  /** Pre-flight duplicate dialog state.
   *
   * Shape when active:
   *   { matches: enrichedMatches[], _resolver: (decisions) => void }
   * The host page (AddItem.jsx) reads this to mount the dialog and
   * calls `resolvePreflight(decisions)` to feed the resolver. */
  preflight: null,
};

const _listeners = new Set();
const _batchSettledListeners = new Set();

/** Per-card in-flight guard to ensure idempotency under React strict
 * mode + manual retries. */
const _analyzeInFlight = new Set();

/** Per-batch awaitable resolver registry. */
const _batchTracking = new Map();
// batchId -> {
//   resolve, reject,                  // Promise hooks (awaitable mode)
//   autoSave,
//   onSettled,                        // optional caller-supplied callback
//   pending: Set<cardId>,             // cards not yet terminal
//   saved: [],                        // server item docs
//   failed: [],                       // {filename, error}
//   navigatedAlready: bool,
// }

function _notify() {
  // Schedule a drain check on every notify so the auto-save queue
  // drives itself even when no React host is currently mounted
  // (e.g. user navigated away from /add mid-batch).
  _scheduleDrainCheck();
  _listeners.forEach((fn) => {
    try { fn(); } catch { /* swallow */ }
  });
}

function _set(patch) {
  _state = { ..._state, ...patch };
  _notify();
}

function _setCards(updater) {
  const next = typeof updater === 'function' ? updater(_state.cards) : updater;
  if (next === _state.cards) return;
  _set({ cards: next });
}

function _generateId(prefix = '') {
  return `${prefix}${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/** Tag a card with its parent batch so settle() can attribute saved
 * /failed counts back to the right resolver. */
function _attachBatchId(card, batchId) {
  return batchId ? { ...card, _batchId: batchId } : card;
}

/* ============================================================
 *  Pipeline: fingerprinting + pre-flight duplicate detection.
 * ============================================================ */

async function _fingerprintFiles(files) {
  return Promise.all(
    files.map(async (f) => {
      const [sha256, phash, color_sig] = await Promise.all([
        sha256File(f),
        aHashFile(f),
        colorSignatureFile(f),
      ]);
      return {
        file: f,
        sha256,
        phash,
        color_sig,
        filename: f.name || null,
        size_bytes: typeof f.size === 'number' ? f.size : null,
      };
    }),
  );
}

function _lookupDuplicates(fingerprints) {
  try {
    const fpForLookup = fingerprints
      .filter((fp) => fp.sha256 || fp.phash)
      .map((fp) => ({
        sha256: fp.sha256 || null,
        phash: fp.phash || null,
        color_sig: fp.color_sig || null,
        filename: fp.filename,
        size_bytes: fp.size_bytes,
      }));
    if (!fpForLookup.length) return [];
    const closetItems = closetStore.getSnapshot().items || [];
    const res = findDuplicatesInCloset(fpForLookup, closetItems);
    return Array.isArray(res?.matches) ? res.matches : [];
  } catch {
    return [];
  }
}

/* ============================================================
 *  Pipeline: draft builder (was AddItem.continueInteractive).
 * ============================================================ */

async function _buildDrafts(fingerprints, acks, batchId) {
  return Promise.all(
    fingerprints.map(async (fp) => {
      const file = fp.file;
      const b64 = await _fileToBase64(file);
      const isDup =
        (fp.sha256 && acks.sha.has(fp.sha256)) ||
        (fp.phash && acks.ph.has(fp.phash));
      return _attachBatchId({
        id: _generateId(),
        file,
        mime: file.type || 'image/jpeg',
        previewUrl: URL.createObjectURL(file),
        base64: b64,
        status: 'scanning',
        progress: 4,
        fields: _blankFields(),
        error: null,
        label: null,
        sourceSha256: fp.sha256 || null,
        sourcePhash: fp.phash || null,
        sourceColorSig: fp.color_sig || null,
        sourceFilename: fp.filename || null,
        sourceSizeBytes: fp.size_bytes || null,
        isDuplicate: !!isDup,
      }, batchId);
    }),
  );
}

/* ============================================================
 *  Pipeline: per-card streaming analyzer (was AddItem.analyzeCard).
 * ============================================================ */

async function _analyzeCard(card, user) {
  // Idempotency guard — see Patch 12 comment in plan.md.
  if (_analyzeInFlight.has(card.id)) {
    // eslint-disable-next-line no-console
    console.warn(
      `[uploadItems._analyzeCard] skipped duplicate analyze for card ${card.id}`,
    );
    return;
  }
  _analyzeInFlight.add(card.id);
  workStore.registerAnalyze(
    card.id,
    card.sourceFilename || card.file?.name || null,
  );

  const startedAt = Date.now();
  const tick = setInterval(() => {
    const elapsed = (Date.now() - startedAt) / 1000;
    const target = Math.min(92, 4 + elapsed * 5);
    _setCards((prev) =>
      prev.map((c) =>
        c.id === card.id && c.status === 'scanning'
          ? { ...c, progress: target }
          : c,
      ),
    );
  }, 250);

  try {
    const requestLang = (i18n.language || '').split('-')[0] || 'en';
    let perCardIds = [];

    // Builds a fresh placeholder card from a single garment detect
    // meta. CRITICAL: must propagate the source-photo fingerprints
    // from the parent card so saved items carry sha256/phash and
    // the closet hash-repair / thumb-repair streams don't mistake
    // them for legacy items (Patch M20.5.2).
    const _buildPlaceholder = (meta, cardId) =>
      _attachBatchId({
        id: cardId,
        file: null,
        mime: meta.crop_mime || 'image/jpeg',
        previewUrl: meta.crop_base64
          ? `data:${meta.crop_mime || 'image/jpeg'};base64,${meta.crop_base64}`
          : card.previewUrl,
        base64: meta.crop_base64 || card.base64,
        originalCropUrl: meta.crop_base64
          ? `data:${meta.crop_mime || 'image/jpeg'};base64,${meta.crop_base64}`
          : null,
        reconstructedUrl: null,
        reconstructedB64: null,
        reconstructionMeta: null,
        useReconstructed: false,
        status: 'scanning',
        progress: 60,
        fields: _hydrate({}, user),
        error: null,
        label: meta.label || null,
        potentialDuplicate: null,
        fromOnePass: false,
        reconstructionAdvised: false,
        deferMatte: !!meta.defer_matte,
        // Inherit source fingerprints from the parent draft. See
        // M20.5.2 root-cause writeup in plan.md.
        sourceSha256: card.sourceSha256 || null,
        sourcePhash: card.sourcePhash || null,
        sourceColorSig: card.sourceColorSig || null,
        sourceFilename: card.sourceFilename || null,
        sourceSizeBytes: card.sourceSizeBytes || null,
        isDuplicate: !!card.isDuplicate,
        _streamSlot: meta._slot,
      }, card._batchId);

    const handleDetect = (frame) => {
      const metas = (frame.items_meta || []).map((m, i) => ({
        ...m,
        _slot: i,
      }));
      if (metas.length === 0) return;
      workStore.updateAnalyze(card.id, { items: 0, total: metas.length });
      const newIds = metas.map((_m, i) => `${card.id}-${i}`);
      perCardIds = newIds;
      const placeholders = metas.map((m, i) => _buildPlaceholder(m, newIds[i]));
      _setCards((prev) => {
        const idx = prev.findIndex((c) => c.id === card.id);
        if (idx < 0) return prev;
        return [...prev.slice(0, idx), ...placeholders, ...prev.slice(idx + 1)];
      });
      if (card.previewUrl?.startsWith('blob:')) {
        URL.revokeObjectURL(card.previewUrl);
      }
      // Migrate the per-batch pending set: parent card id is gone,
      // its slots are now in play.
      if (card._batchId) {
        const tracking = _batchTracking.get(card._batchId);
        if (tracking) {
          tracking.pending.delete(card.id);
          for (const slotId of newIds) tracking.pending.add(slotId);
        }
      }
    };

    const handleItem = (frame) => {
      const slotId = perCardIds[frame.index];
      if (!slotId) return;
      const job = workStore.getSnapshot().analyzeJobs[card.id];
      if (job) {
        workStore.updateAnalyze(card.id, {
          items: Math.min((job.items || 0) + 1, job.total || (job.items + 1)),
        });
      }
      const rec = frame.reconstruction;
      const recValidated = !!(rec && rec.validated && rec.image_b64);
      const reconstructedUrl = recValidated
        ? `data:${rec.mime_type || 'image/png'};base64,${rec.image_b64}`
        : null;
      _setCards((prev) =>
        prev.map((c) =>
          c.id === slotId
            ? {
                ...c,
                status: 'ready',
                progress: 100,
                fields: _hydrate(frame.analysis || {}, user),
                label: frame.label || c.label,
                potentialDuplicate: frame.potential_duplicate || null,
                fromOnePass: !!frame.one_pass,
                reconstructionAdvised: !!frame.reconstruction_advised,
                deferMatte: !!frame.defer_matte,
                needsReconstruction: !!frame.needs_reconstruction,
                reconstructionReasons: frame.reconstruction_reasons || [],
                reconstructedUrl,
                reconstructedB64: recValidated ? rec.image_b64 : null,
                reconstructionMeta: recValidated
                  ? {
                      reasons: rec.reasons || [],
                      prompt: rec.prompt,
                      model: rec.model,
                      mime_type: rec.mime_type,
                    }
                  : null,
                useReconstructed: recValidated,
                previewUrl: recValidated ? reconstructedUrl : c.previewUrl,
              }
            : c,
        ),
      );
    };

    const handleItemSkip = (frame) => {
      const slotId = perCardIds[frame.index];
      if (!slotId) return;
      _setCards((prev) => prev.filter((c) => c.id !== slotId));
      // Drop from batch tracker — this slot will never produce a
      // saveable card.
      if (card._batchId) {
        const tracking = _batchTracking.get(card._batchId);
        if (tracking) tracking.pending.delete(slotId);
      }
    };

    const resp = await api.analyzeItemImage(
      { image_base64: card.base64, language: requestLang },
      {
        onDetect: handleDetect,
        onItem: handleItem,
        onItemSkip: handleItemSkip,
      },
    );
    clearInterval(tick);

    const finalCount = resp?.count || (resp?.items || []).length;
    if (finalCount === 0) {
      _setCards((prev) =>
        prev.map((c) =>
          c.id === card.id
            ? {
                ...c,
                status: 'error',
                progress: 0,
                error: _t('addItem.analyzeFailed'),
                analyzeError: true,
              }
            : c,
        ),
      );
      toast.error(_t('addItem.analyzeFailed'));
      return;
    }
    toast.success(_t('addItem.detected', { count: finalCount }));
  } catch (err) {
    clearInterval(tick);
    const msg =
      err?.response?.data?.detail ||
      err?.message ||
      _t('addItem.analyzeFailed');
    _setCards((prev) =>
      prev.map((c) =>
        c.id === card.id
          ? { ...c, status: 'error', progress: 0, error: msg, analyzeError: true }
          : c,
      ),
    );
    toast.error(msg);
  } finally {
    _analyzeInFlight.delete(card.id);
    workStore.completeAnalyze(card.id);
    _maybeAdvanceBatchAfterAnalyze(card._batchId);
  }
}

/* ============================================================
 *  Pipeline: payload builder + save (was buildCreatePayload /
 *  saveAll).
 * ============================================================ */

function _buildCreatePayload(card) {
  const f = card.fields || {};
  const asBase64 = card.base64;
  const body = {
    source:
      f.marketplace_intent && f.marketplace_intent !== _INTENT_OWN
        ? _SOURCE_SHARED
        : _SOURCE_PRIVATE,
    name: f.name || undefined,
    title: f.name || f.title || 'Unnamed garment',
    caption: f.caption || undefined,
    category: f.category || 'Top',
    sub_category: f.sub_category || undefined,
    item_type: f.item_type || undefined,
    brand: f.brand || undefined,
    gender: f.gender || undefined,
    dress_code: f.dress_code || undefined,
    season: f.season || [],
    tradition: f.tradition || undefined,
    size: f.size || undefined,
    color: (f.colors && f.colors[0]?.name) || undefined,
    colors: (f.colors || []).filter((c) => c.name),
    fabric_materials: (f.fabric_materials || []).filter((c) => c.name),
    pattern: f.pattern || undefined,
    state: f.state || undefined,
    condition: f.condition || undefined,
    quality: f.quality || undefined,
    repair_advice: f.repair_advice || undefined,
    price_cents:
      f.price_cents === '' || f.price_cents == null ? 0 : Number(f.price_cents),
    currency: f.currency || 'USD',
    marketplace_intent: f.marketplace_intent || _INTENT_OWN,
    tags: f.tags || [],
    image_base64: asBase64 || undefined,
    image_mime: asBase64
      ? card.mime || card.file?.type || 'image/jpeg'
      : undefined,
    reconstructed_image_b64:
      card.useReconstructed && card.reconstructedB64
        ? card.reconstructedB64
        : undefined,
    reconstruction_metadata:
      card.useReconstructed && card.reconstructionMeta
        ? card.reconstructionMeta
        : undefined,
    dpp_data: card.dppData || undefined,
    source_sha256: card.sourceSha256 || undefined,
    source_phash: card.sourcePhash || undefined,
    source_color_sig: card.sourceColorSig || undefined,
    source_filename: card.sourceFilename || undefined,
    source_size_bytes:
      typeof card.sourceSizeBytes === 'number' ? card.sourceSizeBytes : undefined,
    is_duplicate: card.isDuplicate ? true : undefined,
    from_one_pass: card.fromOnePass ? true : undefined,
    defer_matte: card.deferMatte ? true : undefined,
  };
  return Object.fromEntries(
    Object.entries(body).filter(([, v]) => v !== undefined),
  );
}

async function _saveAll(opts = {}) {
  const { user } = opts;
  const cards = _state.cards;
  const ready = cards.filter(
    (c) => c.status === 'ready' || c.status === 'error',
  );
  const scanning = cards.filter((c) => c.status === 'scanning');

  if (!ready.length && !scanning.length) {
    toast.error(_t('addItem.nothingToSave'));
    return { saved: [], failed: [] };
  }

  // All scanning -> queue and bail; the auto-save drain will re-fire.
  if (!ready.length) {
    _set({ pendingAutoSave: true });
    toast.info(
      _t('addItem.queuedForAutoSave', {
        count: scanning.length,
        defaultValue:
          scanning.length === 1
            ? 'Waiting for 1 photo to finish analysing — will save automatically.'
            : `Waiting for ${scanning.length} photos to finish analysing — will save automatically.`,
      }),
    );
    return { saved: [], failed: [] };
  }

  _set({ saving: true });

  const validCards = [];
  const skipped = [];
  for (const card of ready) {
    if (card.status === 'error' && !card.fields?.title) {
      skipped.push(card);
      continue;
    }
    try {
      const body = _buildCreatePayload(card);
      if (!body.title) throw new Error('Title is required');
      validCards.push({ card, body });
    } catch (err) {
      skipped.push({ ...card, _buildErr: err });
    }
  }

  if (skipped.length) {
    _setCards((prev) =>
      prev.map((c) =>
        skipped.find((s) => s.id === c.id)
          ? { ...c, status: 'error', error: c.error || 'Title is required' }
          : c,
      ),
    );
  }
  if (!validCards.length) {
    _set({ saving: false });
    toast.error(_t('addItem.noneSaved'));
    return { saved: [], failed: [] };
  }

  // Step 1+2 — optimistic ghosts into closetStore.
  const ghosts = new Map();
  const nowIso = new Date().toISOString();
  for (const { card, body } of validCards) {
    const tempId =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    const dataUrl = card.base64
      ? `data:${card.mime || card.file?.type || 'image/jpeg'};base64,${card.base64}`
      : card.previewUrl || null;
    const filename = card.sourceFilename || card.file?.name || null;
    const optimisticItem = {
      id: tempId,
      user_id: undefined,
      source: body.source || _SOURCE_PRIVATE,
      name: body.name || body.title,
      title: body.title,
      caption: body.caption || null,
      category: body.category || 'Top',
      sub_category: body.sub_category || null,
      item_type: body.item_type || null,
      brand: body.brand || null,
      gender: body.gender || null,
      dress_code: body.dress_code || null,
      season: body.season || [],
      size: body.size || null,
      color: body.color || null,
      colors: body.colors || [],
      fabric_materials: body.fabric_materials || [],
      pattern: body.pattern || null,
      state: body.state || null,
      condition: body.condition || null,
      quality: body.quality || null,
      price_cents: body.price_cents || 0,
      currency: body.currency || 'USD',
      marketplace_intent: body.marketplace_intent || _INTENT_OWN,
      tags: body.tags || [],
      original_image_url: dataUrl,
      thumbnail_data_url: dataUrl,
      created_at: nowIso,
      updated_at: nowIso,
      source_sha256: body.source_sha256 || null,
      source_filename: filename,
      source_phash: body.source_phash || null,
      source_color_sig: body.source_color_sig || null,
      is_duplicate: !!body.is_duplicate,
      _pendingSync: true,
    };
    ghosts.set(tempId, {
      body,
      title: optimisticItem.title,
      thumbnail: dataUrl,
      filename,
      cardId: card.id,
      batchId: card._batchId || null,
    });
    closetStore.upsert(optimisticItem);
    _setCards((prev) =>
      prev.map((c) => (c.id === card.id ? { ...c, status: 'saved' } : c)),
    );
  }

  const stillScanning = _state.cards.some((c) => c.status === 'scanning');
  if (stillScanning) {
    toast.info(
      _t('addItem.savedSomeWaitingForRest', {
        saved: validCards.length,
        remaining: _state.cards.filter((c) => c.status === 'scanning').length,
        defaultValue:
          `Saved ${validCards.length} — waiting for ${_state.cards.filter((c) => c.status === 'scanning').length} more to finish analysing.`,
      }),
    );
    _set({ pendingAutoSave: true, saving: false });
  } else {
    toast.success(
      _t('addItem.savedOptimistic', {
        count: validCards.length,
        defaultValue:
          validCards.length === 1
            ? 'Added to your closet — syncing in background'
            : `${validCards.length} items added to your closet — syncing in background`,
      }),
    );
    _set({ saving: false, pendingAutoSave: false });
  }

  // Step 3+4 — parallel persistence + reconcile in the background.
  const tempIds = Array.from(ghosts.keys());
  const results = await Promise.allSettled(
    tempIds.map((tid) => api.createItem(ghosts.get(tid).body)),
  );
  const polishCandidates = [];
  const savedItems = [];
  const failedItems = [];
  for (let i = 0; i < results.length; i += 1) {
    const tid = tempIds[i];
    const g = ghosts.get(tid);
    const r = results[i];
    if (r.status === 'fulfilled' && r.value && r.value.id) {
      closetStore.remove(tid);
      closetStore.upsert(r.value);
      savedItems.push(r.value);
      if (r.value.clean_image_status === 'pending') {
        polishCandidates.push(r.value);
      }
      _maybeAdvanceBatchAfterSave(g.batchId, g.cardId, {
        ok: true,
        item: r.value,
      });
    } else {
      closetStore.remove(tid);
      const detail =
        (r.reason && (r.reason.response?.data?.detail || r.reason.message)) ||
        'Save failed';
      failedItems.push({
        id: tid,
        title: g.title,
        filename: g.filename,
        thumbnail: g.thumbnail,
        error: detail,
      });
      _maybeAdvanceBatchAfterSave(g.batchId, g.cardId, {
        ok: false,
        error: detail,
      });
    }
  }
  if (polishCandidates.length) {
    workStore.registerPolishItems(polishCandidates);
  }
  if (failedItems.length) {
    closetStore.recordSaveFailures(failedItems);
  }
  return { saved: savedItems, failed: failedItems };
}

/* ============================================================
 *  Pipeline: orchestration (was handleFiles / handleBulkUpload).
 * ============================================================ */

async function _runStart(files, opts) {
  const {
    user,
    autoSave,
    autoResolveDuplicates,
    batchId,
  } = opts;

  if (!files.length) {
    _finalizeBatch(batchId);
    return;
  }
  const fingerprints = await _fingerprintFiles(files);
  const matches = _lookupDuplicates(fingerprints);

  let survivors = fingerprints;
  let acks = { sha: new Set(), ph: new Set() };
  let skippedCount = 0;

  if (matches.length) {
    if (autoResolveDuplicates === 'skip') {
      const dupShas = new Set(matches.map((m) => m.sha256).filter(Boolean));
      const dupPhashes = new Set(matches.map((m) => m.phash).filter(Boolean));
      survivors = fingerprints.filter(
        (fp) =>
          !(fp.sha256 && dupShas.has(fp.sha256)) &&
          !(fp.phash && dupPhashes.has(fp.phash)),
      );
      skippedCount = fingerprints.length - survivors.length;
    } else if (autoResolveDuplicates === 'add-all') {
      for (const m of matches) {
        if (m.sha256) acks.sha.add(m.sha256);
        if (m.phash) acks.ph.add(m.phash);
      }
    } else {
      // 'prompt' mode — surface the dialog, wait for resolvePreflight.
      const matchesEnriched = matches.map((m) => {
        const fp = fingerprints.find(
          (x) =>
            (m.sha256 && x.sha256 === m.sha256) ||
            (m.phash && x.phash === m.phash),
        );
        const file = fp?.file;
        const previewUrl = file ? URL.createObjectURL(file) : null;
        const matchKey = m.sha256 || m.phash || `${m.filename}-${m.size_bytes}`;
        return { ...m, previewUrl, matchKey };
      });
      _set({
        preflight: {
          matches: matchesEnriched,
          _resolver: (decisions) => {
            matchesEnriched.forEach((m) => {
              if (m.previewUrl?.startsWith('blob:')) {
                URL.revokeObjectURL(m.previewUrl);
              }
            });
            _set({ preflight: null });
            const survivorsAfter = fingerprints.filter((fp) => {
              for (const m of matchesEnriched) {
                const matched =
                  (m.sha256 && fp.sha256 === m.sha256) ||
                  (m.phash && fp.phash === m.phash);
                if (matched) return decisions[m.matchKey] === 'add';
              }
              return true;
            });
            if (!survivorsAfter.length) {
              toast.message(
                _t('addItem.preflight.allSkipped', {
                  defaultValue:
                    'All selected photos were duplicates and were skipped.',
                }),
              );
              _finalizeBatch(batchId);
              return;
            }
            const innerAcks = { sha: new Set(), ph: new Set() };
            matchesEnriched.forEach((m) => {
              if (decisions[m.matchKey] === 'add') {
                if (m.sha256) innerAcks.sha.add(m.sha256);
                if (m.phash) innerAcks.ph.add(m.phash);
              }
            });
            _kickAnalyzePipeline(survivorsAfter, innerAcks, user, batchId, autoSave);
          },
        },
      });
      return; // wait for the dialog
    }
  }

  if (skippedCount > 0) {
    toast.message(
      _t('addItem.preflight.someDuplicatesSkipped', {
        count: skippedCount,
        defaultValue: `Skipped ${skippedCount} photo${skippedCount === 1 ? '' : 's'} already in your closet.`,
      }),
    );
  }
  if (!survivors.length) {
    toast.message(
      _t('addItem.preflight.allDuplicatesSkippedBatch', {
        count: skippedCount,
        defaultValue: `Skipped ${skippedCount} photos already in your closet — nothing new to upload.`,
      }),
    );
    _finalizeBatch(batchId);
    return;
  }
  _kickAnalyzePipeline(survivors, acks, user, batchId, autoSave);
}

async function _kickAnalyzePipeline(fingerprints, acks, user, batchId, autoSave) {
  const drafts = await _buildDrafts(fingerprints, acks, batchId);
  if (batchId) {
    const tracking = _batchTracking.get(batchId);
    if (tracking) {
      drafts.forEach((d) => tracking.pending.add(d.id));
    }
  }
  _setCards((prev) => [...prev, ...drafts]);
  drafts.forEach((d) => _analyzeCard(d, user));
  if (autoSave) {
    _set({ pendingAutoSave: true });
  }
}

/* ============================================================
 *  Batch tracking (for awaitable mode + onBatchSettled).
 * ============================================================ */

function _maybeAdvanceBatchAfterAnalyze(batchId) {
  // Analysis ended (success or error) for one card. If autoSave is
  // on and no cards are scanning, the drain effect will re-fire
  // saveAll. We don't settle until saveAll completes.
  if (!batchId) return;
  // No-op here; settlement happens in _maybeAdvanceBatchAfterSave or
  // when no scanning cards remain AND autoSave is off — in that
  // case the user must click Save explicitly.
}

function _maybeAdvanceBatchAfterSave(batchId, cardId, outcome) {
  if (!batchId) return;
  const tracking = _batchTracking.get(batchId);
  if (!tracking) return;
  tracking.pending.delete(cardId);
  if (outcome.ok) tracking.saved.push(outcome.item);
  else tracking.failed.push({ cardId, error: outcome.error });
  if (tracking.pending.size === 0) _finalizeBatch(batchId);
}

function _finalizeBatch(batchId) {
  if (!batchId) return;
  const tracking = _batchTracking.get(batchId);
  if (!tracking) return;
  _batchTracking.delete(batchId);
  const result = { saved: tracking.saved, failed: tracking.failed };
  try {
    if (typeof tracking.onSettled === 'function') tracking.onSettled(result);
  } catch { /* swallow */ }
  if (typeof tracking.resolve === 'function') tracking.resolve(result);
  _batchSettledListeners.forEach((fn) => {
    try { fn(result); } catch { /* swallow */ }
  });
}

/* ============================================================
 *  Auto-save drain — module-level so it doesn't depend on the
 *  host page being mounted.
 * ============================================================ */

let _drainScheduled = false;
function _scheduleDrainCheck() {
  if (_drainScheduled) return;
  _drainScheduled = true;
  queueMicrotask(() => {
    _drainScheduled = false;
    if (!_state.pendingAutoSave) return;
    const stillScanning = _state.cards.some((c) => c.status === 'scanning');
    if (stillScanning) return;
    // Reset BEFORE the call so a re-fire from settle() can re-arm it.
    _set({ pendingAutoSave: false });
    _saveAll({ user: _lastKnownUser });
  });
}

// Track the most recently-seen user so the drain has someone to
// hydrate sizes against. Hook callers update this on mount.
let _lastKnownUser = null;

/* ============================================================
 *  Public API.
 * ============================================================ */

export const uploadItems = Object.freeze({
  getSnapshot() {
    return _state;
  },

  subscribe(fn) {
    _listeners.add(fn);
    return () => _listeners.delete(fn);
  },

  onBatchSettled(fn) {
    _batchSettledListeners.add(fn);
    return () => _batchSettledListeners.delete(fn);
  },

  /**
   * Canonical entry point. See top-of-file docstring for the full
   * contract.
   */
  start(fileList, opts = {}) {
    const files = Array.from(fileList || []);
    const mode = opts.mode === 'awaitable' ? 'awaitable' : 'fire-and-forget';
    const autoSave = opts.autoSave === true; // default false (manual save)
    const autoResolveDuplicates =
      opts.autoResolveDuplicates === 'skip'
        ? 'skip'
        : opts.autoResolveDuplicates === 'add-all'
          ? 'add-all'
          : 'prompt';
    const user = opts.user || _lastKnownUser;

    const batchId = _generateId('batch-');
    const tracking = {
      pending: new Set(),
      saved: [],
      failed: [],
      autoSave,
      onSettled: opts.onSettled,
      resolve: null,
      reject: null,
    };
    _batchTracking.set(batchId, tracking);

    let promise = null;
    if (mode === 'awaitable') {
      promise = new Promise((resolve, reject) => {
        tracking.resolve = resolve;
        tracking.reject = reject;
      });
    }

    _runStart(files, {
      user,
      autoSave,
      autoResolveDuplicates,
      batchId,
    }).catch((err) => {
      _batchTracking.delete(batchId);
      if (mode === 'awaitable') tracking.reject?.(err);
      else {
        // eslint-disable-next-line no-console
        console.error('[uploadItems.start] unexpected failure', err);
      }
    });

    return mode === 'awaitable' ? promise : undefined;
  },

  saveAll(opts = {}) {
    return _saveAll({ user: opts.user || _lastKnownUser });
  },

  removeCard(cardId) {
    _setCards((prev) => {
      const target = prev.find((c) => c.id === cardId);
      if (target?.previewUrl?.startsWith('blob:')) {
        URL.revokeObjectURL(target.previewUrl);
      }
      return prev.filter((c) => c.id !== cardId);
    });
  },

  retryCard(cardId, opts = {}) {
    const card = _state.cards.find((c) => c.id === cardId);
    if (!card) return;
    _setCards((prev) =>
      prev.map((c) =>
        c.id === cardId
          ? { ...c, status: 'scanning', progress: 4, error: null, analyzeError: false }
          : c,
      ),
    );
    _analyzeCard(card, opts.user || _lastKnownUser);
  },

  updateField(cardId, patch) {
    _setCards((prev) =>
      prev.map((c) =>
        c.id === cardId ? { ...c, fields: { ...c.fields, ...patch } } : c,
      ),
    );
  },

  patchCard(cardId, patch) {
    _setCards((prev) =>
      prev.map((c) => (c.id === cardId ? { ...c, ...patch } : c)),
    );
  },

  hydrateFromDpp(res, user) {
    const items = res?.items || [];
    const first = items[0] || {};
    const analysis = first.analysis || {};
    const dppData = first.dpp_data || null;
    const hasImage = !!first.crop_base64;
    const mime = first.crop_mime || 'image/png';
    const previewUrl = hasImage
      ? `data:${mime};base64,${first.crop_base64}`
      : null;
    const draft = {
      id: _generateId('dpp-'),
      file: null,
      mime: hasImage ? mime : null,
      previewUrl,
      base64: hasImage ? first.crop_base64 : null,
      status: 'ready',
      progress: 100,
      fields: _hydrate(analysis, user || _lastKnownUser),
      error: null,
      label: first.label || analysis.item_type || null,
      dppData,
      source: 'dpp',
    };
    _setCards((prev) => [draft, ...prev]);
    toast.success(_t('dpp.scanner.imported'));
  },

  resolvePreflight(decisions, _user) {
    const pf = _state.preflight;
    if (!pf || typeof pf._resolver !== 'function') {
      _set({ preflight: null });
      return;
    }
    pf._resolver(decisions || {});
  },

  clearPreflight() {
    // Treat as "discard everything" — resolver fires with no
    // decisions so survivorsAfter ends up empty.
    const pf = _state.preflight;
    if (pf && typeof pf._resolver === 'function') {
      pf._resolver({});
    } else {
      _set({ preflight: null });
    }
  },

  acceptDuplicate(cardId) {
    _setCards((prev) =>
      prev.map((c) =>
        c.id === cardId ? { ...c, duplicateConfirmed: true } : c,
      ),
    );
  },

  discardDuplicate(cardId) {
    _setCards((prev) => {
      const removed = prev.find((c) => c.id === cardId);
      if (removed?.previewUrl?.startsWith('blob:')) {
        URL.revokeObjectURL(removed.previewUrl);
      }
      return prev.filter((c) => c.id !== cardId);
    });
  },

  /** Test/triage hook. Clears all state and in-flight trackers. */
  reset() {
    _state = {
      cards: [],
      saving: false,
      pendingAutoSave: false,
      preflight: null,
    };
    _analyzeInFlight.clear();
    _batchTracking.clear();
    _notify();
  },
});

/* ============================================================
 *  React hook (reactive wrapper).
 * ============================================================ */

/**
 * useUploadItems — reactive bindings for React pages.
 *
 * `opts.user` (recommended) — the auth user object. Required for size
 * preference hydration. Pages typically pass `useAuth().user`.
 *
 * `opts.onBatchSettled` (optional) — fires with `{saved, failed}`
 * when a batch settles. Useful for navigating to /closet on success.
 *
 * Returns an object containing:
 *   - the entire `getSnapshot()` state (cards, saving, pendingAutoSave,
 *     preflight)
 *   - bound mutators that auto-forward `user`
 */
export function useUploadItems(opts = {}) {
  const snapshot = useSyncExternalStore(
    uploadItems.subscribe,
    uploadItems.getSnapshot,
    uploadItems.getSnapshot,
  );

  // Keep the module-level _lastKnownUser in sync with the most recently
  // mounted host. This lets the auto-save drain hydrate sizes even when
  // the host page has unmounted (e.g. user navigated away mid-batch).
  useEffect(() => {
    if (opts.user) _lastKnownUser = opts.user;
  }, [opts.user]);

  // Note: the auto-save drain runs at the module level (triggered by
  // every `_notify()`), so it does NOT depend on this hook being
  // mounted. A batch initiated on /add will continue to drain and
  // navigate even if the user wanders off mid-batch.

  // Wire the optional onBatchSettled callback.
  useEffect(() => {
    if (typeof opts.onBatchSettled !== 'function') return undefined;
    return uploadItems.onBatchSettled(opts.onBatchSettled);
  }, [opts.onBatchSettled]);

  return {
    // State (reactive)
    cards: snapshot.cards,
    saving: snapshot.saving,
    pendingAutoSave: snapshot.pendingAutoSave,
    preflight: snapshot.preflight,

    // Mutators (bound)
    start: (files, o = {}) =>
      uploadItems.start(files, { user: opts.user, ...o }),
    saveAll: (o = {}) => uploadItems.saveAll({ user: opts.user, ...o }),
    removeCard: uploadItems.removeCard,
    retryCard: (cardId) =>
      uploadItems.retryCard(cardId, { user: opts.user }),
    updateField: uploadItems.updateField,
    patchCard: uploadItems.patchCard,
    hydrateFromDpp: (res) => uploadItems.hydrateFromDpp(res, opts.user),
    resolvePreflight: (decisions) =>
      uploadItems.resolvePreflight(decisions, opts.user),
    clearPreflight: uploadItems.clearPreflight,
    acceptDuplicate: uploadItems.acceptDuplicate,
    discardDuplicate: uploadItems.discardDuplicate,
  };
}
