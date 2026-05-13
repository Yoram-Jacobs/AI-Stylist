# DressApp Shopping Assistant — Manual Install Guide

This is a short walkthrough for testing the unpacked Chrome extension end-to-end on your own browser, before we ship to the Chrome Web Store.

> **TL;DR:** Connect the popup once at `https://dressapp.co/extension/connect`, then click the **DressApp size** pill that appears next to the size picker on supported stores. The recommendation pops up bottom-right.

---

## 1. What you'll need

| Requirement | Notes |
|---|---|
| Chrome / Edge / Brave (Chromium 114+) | Manifest V3 + `chrome.tabs.captureVisibleTab` |
| A DressApp account | The popup needs a valid login on `dressapp.co` (or your preview env) |
| Stored body measurements | Profile → Body measurements → fill in *at least* chest / waist / hip |

The extension never persists your measurements locally; it asks the backend on each open.

---

## 2. Install (load unpacked)

There are two equivalent ways. Pick whichever is easier.

### 2A. From the prebuilt `dressapp-extension.zip`

1. Download `dressapp-extension.zip` from `/app/chrome-extension/dressapp-extension.zip` and unzip it anywhere on disk (e.g. `~/dressapp-ext/`).
2. Open `chrome://extensions/`.
3. Toggle **Developer mode** on (top-right).
4. Click **Load unpacked**.
5. Select the unzipped folder (the one that contains `manifest.json`).
6. Confirm the extension card shows **DressApp Shopping Assistant** with no error banner.
7. Pin it to the toolbar so you can open the popup easily (puzzle-piece icon → pin).

### 2B. From the repo build folder

1. From the repo, run:

   ```bash
   cd /app/chrome-extension
   yarn install   # only first time
   yarn build
   ```

2. Open `chrome://extensions/`, enable **Developer mode**, click **Load unpacked**, and select `/app/chrome-extension/dist`.

> If you change source files, just re-run `yarn build` and click the **reload** icon on the extension card. No need to remove and re-add.

---

## 3. Connect your account

1. Click the DressApp icon in the toolbar — the popup opens.
2. You should see **Connect to DressApp**. Click it.
3. A new tab opens at `https://dressapp.co/extension/connect?ext_id=…&v=1`.
   * If you're already signed in, the page auto-handshakes and shows **Connected** with a green check, then closes itself.
   * If you're signed out, you'll be redirected to `/login`. After signing in, you'll land back on `/extension/connect` and the handoff continues.
4. Reopen the popup. It should now show your name/email, **Logged in** badge, and a **Measurements** card with your stored values.

> Token storage: the extension keeps the JWT in `chrome.storage.local` only. The popup and content scripts never see it directly — they ask the background service worker, which adds the bearer header on every API call.

---

## 4. Try it on a real store

Supported sites (Manifest V3 host matches):

* `*.zara.com`
* `*.asos.com`
* `*.shein.com`
* `*.hm.com`
* `*.amazon.com|.co.uk|.de|.fr|.it|.es`
* `*.aliexpress.com|.us`

**Flow on each store:**

1. Open a product page (any garment).
2. Look for a black pill button labelled **● DressApp size** next to the size selector or "Size" label. (If your size picker is inside a modal, open the modal first — the button anchors to whichever size control is visible.)
3. Click the pill.
4. The bottom-right corner shows a card:
   * a spinner while reading the chart, then
   * **DressApp recommends size *M*** (with a confidence chip and "Matched on: chest · waist" line), or
   * a fallback message if the chart can't be parsed (with a Retry button).

**What's happening under the hood**

| Path | When | What we send |
|---|---|---|
| HTML chart | Page exposes a `<table>` with size keywords | `chart_html` |
| Image chart | Size guide is rendered as a single `<img>` | `chart_screenshot_b64` (base64 JPEG of the image) |
| Visible-tab capture | Neither of the above worked | `chart_screenshot_b64` (a JPEG of the active tab) |

The backend tries Gemma (Eyes provider) first, falls back to Gemini 2.5 Flash, and finally to a numeric heuristic — so you should always get a 200 response, even on a chart the AI can't fully parse.

---

## 5. Troubleshoot

| Symptom | Likely cause | Fix |
|---|---|---|
| Popup spins forever | Service worker was killed and the popup can't reach it | Close + reopen the popup. If still broken, click **Reload** on the extension card. |
| Popup shows **Couldn't load extension state** | Token expired / revoked | Click **Sign out of extension**, then **Connect to DressApp** again. |
| **DressApp size** button never appears | The store's size picker uses a non-standard DOM that our adapters didn't pick up | Open the size selector / size guide modal, then *click the page once*. The MutationObserver will retry the mount. If still missing, enable debug logs (see below) and report the page URL. |
| Overlay says **No size chart found** | The chart is hidden behind a click-to-open modal, or this product simply has no size table | Open the size-guide modal, then click DressApp again. The image/screenshot fallback will fire. |
| Overlay says **Add your measurements** | Your DressApp profile has no chest/waist/hip values | Click the link to **Open profile**, fill in measurements, then retry. |
| Connect tab opens but never closes | The handoff content script wasn't injected (manifest URL pattern mismatch) | Make sure the URL is exactly `https://dressapp.co/extension/connect` or your preview origin (`*.preview.emergentagent.com`). Other origins are rejected on purpose. |

### Debug logs

The content script logs verbosely when you opt-in:

```js
// In the DevTools console of any shopping site:
localStorage.setItem('dressapp_debug', '1');
```

You'll see entries like `[DressApp/zara] button mounted next to <select…>` and `[DressApp/asos] analyze payload (preview) {…}`.

To turn off: `localStorage.removeItem('dressapp_debug')`.

---

## 6. Privacy summary (for the future Web-Store listing)

* The extension only activates on the listed shopping origins and the auth-bridge URL.
* On click, it forwards the size chart (HTML or a JPEG screenshot) and your stored measurements to your DressApp backend over HTTPS.
* No browsing history, page contents, or PII outside the chart area is captured or stored.
* The session token is stored only in `chrome.storage.local` and is removed when you sign out from the popup.

---

## 7. File map (for the curious)

```
chrome-extension/
├── manifest.json                       # MV3 manifest (icons, content scripts, externally_connectable)
├── icons/                              # 16/32/48/128 PNGs
└── src/
    ├── popup/                          # React popup (Tailwind)
    ├── background/service-worker.js    # Auth + API + tab capture
    ├── content/
    │   ├── content.js                  # Button injection + analyze flow
    │   ├── overlay.js                  # Floating recommendation card
    │   ├── content.css                 # Scoped styles
    │   ├── auth-bridge.js              # Listens on /extension/connect
    │   └── adapters/
    │       ├── sites.js                # Per-store selectors
    │       └── generic.js              # Fallback chart/anchor/image detection
    └── lib/
        ├── api.js                      # Backend client (bearer header)
        └── messages.js                 # SW <-> popup <-> content message catalogue
```

---

Found a bug or DOM mismatch on a specific product page? Note the store URL and DOM selector that the **DressApp size** button *should* have anchored to — that's the fastest path to a follow-up adapter tweak.
