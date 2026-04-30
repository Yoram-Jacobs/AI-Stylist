# dressapp.co — Recovery checklist (Hetzner-only, post Emergent-host migration)

You said you no longer use `https://ai-stylist-api.emergent.host`. Right
now `dressapp.co` is **broken** because its DNS is still pointed at
infrastructure (AWS) that 301-redirects the root to the Emergent host
and 404/405's every `/api/*` path. This file walks through the exact
steps to bring `dressapp.co` back to life on your Hetzner VPS.

---

## 0 · TL;DR

```
dressapp.co  →  A record  →  <YOUR HETZNER IPv4>
                                     ↓
                           docker compose stack
                          (caddy + frontend + backend)
                                     ↓
                              MongoDB Atlas M0
```

Everything else is just verifying each layer.

---

## 1 · Confirm what's currently happening (5 min)

From any laptop:

```bash
# Should return your Hetzner VPS IP, NOT 15.197.225.x (AWS).
nslookup dressapp.co        # or:  dig +short dressapp.co
# Right now this returns the AWS Route53 IPs, which is the bug.

# Should return 200, not 405.
curl -i -X POST https://dressapp.co/api/v1/auth/dev-bypass \
  -H "Content-Type: application/json" -d '{}'

# Sanity ping the VPS directly (replace IP):
ssh root@<VPS_IP> 'docker ps --format "{{.Names}}\t{{.Status}}"'
```

Expected once fixed:

```
dressapp-backend   Up XX seconds (healthy)
dressapp-frontend  Up XX seconds (healthy)
dressapp-caddy     Up XX seconds
```

---

## 2 · DNS — point dressapp.co back at Hetzner (10 min)

Your domain registrar's DNS panel (GoDaddy / Namecheap / Cloudflare / Hetzner DNS / etc.):

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A    | @    | `<HETZNER_VPS_IPv4>` | 300 |
| A    | www  | `<HETZNER_VPS_IPv4>` | 300 |
| AAAA | @    | `<HETZNER_VPS_IPv6>` (optional) | 300 |

⚠️ **Delete or disable** any of these that may exist from the Emergent
migration:
- Old `A` / `AAAA` records pointing at AWS IPs (anything in `15.197.x.x`).
- Any `CNAME @ → emergent.host` flattened-CNAME records.
- Cloudflare proxy (orange cloud) on `@` and `www` — temporarily set to
  **DNS only** (gray cloud) until you confirm Caddy can complete its
  Let's Encrypt HTTP-01 challenge. You can re-enable proxying afterwards.

Wait 1–5 minutes, then verify:

```bash
dig +short dressapp.co @1.1.1.1
# Expect: <YOUR_HETZNER_IP>
```

---

## 3 · SSH into the VPS (1 min)

```bash
ssh root@<VPS_IP>     # or your `deploy` user
cd /srv/dressapp      # or wherever you cloned the repo
```

If the directory does not exist, the VPS is fresh — go through
`/app/deploy/DEPLOY.md` from step 4 onward (Mongo Atlas + clone +
`.env`). Otherwise continue here.

---

## 4 · Pull latest code (1 min)

This brings in everything we shipped in this session — Phase Z
bundle, the dual-deploy flag, the address autocomplete, the
`/reanalyze` route, the over-cropping fix, etc.

```bash
cd /srv/dressapp
git fetch --all
git status              # should be clean — no uncommitted local edits
git pull --ff-only origin main
git log --oneline -5    # sanity-check the head moved forward
```

If `git pull` complains about local edits to tracked files,
`git stash` them, pull, then decide whether to drop the stash.

---

## 5 · Sanity-check `deploy/.env` (5 min)

```bash
$EDITOR deploy/.env
```

| Key | Required value |
|---|---|
| `DOMAIN` | `dressapp.co` (no scheme, no path) |
| `CADDY_ACME_EMAIL` | `lokoprod@gmail.com` |
| `MONGO_URL` | `mongodb+srv://...` from Atlas (no quotes around it!) |
| `DB_NAME` | e.g. `dressapp_prod` |
| `JWT_SECRET` | 96 hex chars from `openssl rand -hex 48` |
| `GEMINI_API_KEY` | Your direct Google AI Studio key |
| `EMERGENT_LLM_KEY` | Optional dev fallback |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` | Web client whose authorised redirect URIs include `https://dressapp.co/api/v1/auth/google/callback` |
| `GOOGLE_OAUTH_REDIRECT_URI` | **Leave empty** — backend derives it from the request |
| `GOOGLE_OAUTH_POST_LOGIN_REDIRECT` | **Leave empty** |
| `PAYPAL_*` | LIVE creds + webhook ID |
| `GROQ_API_KEY`, `DEEPGRAM_API_KEY`, `OPENWEATHER_API_KEY`, `HF_TOKEN` | Provider keys |
| `ALLOW_DEV_BYPASS` | `false` for real prod, `true` only while you debug |
| `USE_LOCAL_CLOTHING_PARSER` | `true` (CX22 has the headroom) — set to `false` only if you're tight on RAM |
| `AUTO_MATTE_CROPS` | `true` (same logic as above) |

⚠️ No quotes around values. Compose ships the literal `"..."` into the
container env if you wrap them.

---

## 6 · Rebuild & relaunch (10–12 min first time, < 1 min cached)

```bash
cd /srv/dressapp
docker compose -f deploy/docker-compose.yml --env-file deploy/.env \
  up -d --build
```

Tail logs while certs negotiate:

```bash
docker compose -f deploy/docker-compose.yml logs -f
# Look for, in order:
#   caddy   | obtained certificate for dressapp.co
#   backend | Uvicorn running on http://0.0.0.0:8001
#   frontend| nginx started
```

If Caddy logs `certificate_obtain_failed`, DNS hasn't propagated yet —
wait 2 min and `docker compose restart caddy`.

---

## 7 · Smoke-test (3 min)

From your laptop (cache-bypass, no proxy):

```bash
# 1. dev-bypass should return a token (only if ALLOW_DEV_BYPASS=true)
curl -sS -i -X POST https://dressapp.co/api/v1/auth/dev-bypass \
  -H "Content-Type: application/json" -d '{}'
# Expect: HTTP/2 200 + JSON {"access_token":"...","user":{...}}

# 2. Diagnostics — confirms the new dual-deploy markers are loaded
curl -sS https://dressapp.co/api/v1/closet/analyze/version | jq
# Expect to see, among others:
#   "single_instance_classes_v1": true
#   "analyze_serial_lock":        true
#   "use_local_clothing_parser":  true   (because USE_LOCAL_CLOTHING_PARSER=true on the VPS)
#   "auto_matte_crops":           true
#   "torch_installed":            true
#   "rembg_installed":            true
#   "secrets_present":            { gemini_api_key:true, jwt_secret:true, mongo_url:true, ... }

# 3. SPA loads
curl -sS -o /dev/null -w "%{http_code}\n" https://dressapp.co/
# Expect: 200
```

Now open `https://dressapp.co/login` in a browser — you should see the
DressApp login screen, and "Continue as developer" should land you on
`/home`.

---

## 8 · Settings → Contact: visually verify the new autocomplete (2 min)

Now that the UI is back online, take 30 s to confirm the new feature
shipped end-to-end:

1. Log in (Google or password).
2. Profile menu → **Profile & settings** (`/me`).
3. Open the **Contact** accordion.
4. Click the **Country** field → type `germ` → pick **🇩🇪 Germany**.
5. Click into **Street** → type `Brandenburger`.
   - Within ~600 ms two OpenStreetMap suggestions should appear
     (`Brandenburger Teich`, `Brandenburger Tor`, etc.) — picking one
     auto-fills city + region + postal code.
6. Click into **City** → type `Berlin`.
   - The dropdown should narrow to Berlin districts.

Already verified in the preview pod against
`https://nominatim.openstreetmap.org` — see the screenshots from this
session. No API key needed.

---

## 9 · Re-tighten (5 min)

Once everything is green:

- Set `ALLOW_DEV_BYPASS=false` in `deploy/.env` and
  `docker compose ... up -d` to disable the bypass route in production.
- In Cloudflare (if you use it), re-enable the orange-cloud proxy
  on `@` and `www`.
- In Atlas → **Network Access**, replace `0.0.0.0/0` with the VPS IPv4.

---

## 10 · Common gotchas (paste into a sticky note)

| Symptom | Fix |
|---|---|
| `405 Method Not Allowed`, `allow: GET, HEAD` | Means a CDN/load-balancer is intercepting `/api/*` instead of forwarding to Caddy. Re-check DNS — `dig +short dressapp.co` MUST return the Hetzner IP, not an AWS IP. |
| `certificate_obtain_failed` in caddy logs | DNS not propagated, ports 80/443 blocked, or Cloudflare is in "Full (strict)" mode without a real cert. Run `curl -4 ifconfig.me` on the VPS, compare to dig output. |
| Backend logs `pymongo.errors.OperationFailure: bad auth` | Wrong password in `MONGO_URL`. Reset in Atlas → Database Access. |
| Backend logs `MongoDB URI options are key=value pairs` | Trailing `&appName` (no `=`) in `MONGO_URL`. Fix in `.env`. |
| `/api/v1/auth/google/callback` → `redirect_uri_mismatch` | Add `https://dressapp.co/api/v1/auth/google/callback` to the OAuth client in Google Cloud Console. |
| First `/analyze` 30 s | One-time SegFormer + u2netp warm-up; cached afterwards. |
| Browser blocks an `/ads/...` URL | Ad blocker. The repo already renamed `/ads` → `/promotions` — confirm you pulled `git log --oneline | grep promotions`. |
| `/api/v1/closet/analyze/version` shows `use_local_clothing_parser: false` on the VPS | You inherited the lightweight env. Set `USE_LOCAL_CLOTHING_PARSER=true` and `AUTO_MATTE_CROPS=true` in `deploy/.env`, `up -d`. |

---

If after step 7 anything still fails, paste the relevant
`docker compose logs --tail 100 backend` (or caddy / frontend) here
and I'll diagnose further.
