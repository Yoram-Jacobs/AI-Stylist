# Deploying DressApp to Hetzner Cloud

**Target**: single VPS (Hetzner CX22 or larger), docker-compose, Caddy
for automatic HTTPS, MongoDB Atlas free tier for storage. End-to-end
time: ~45 minutes.

```
┌──────────────────────────────┐
│  dressapp.co (your domain)   │
└──────────────┬───────────────┘
               │ 443
       ┌───────▼────────┐
       │   caddy (TLS)  │
       └───┬────────┬───┘
   /api/*  │        │  /*
           │        │
 ┌─────────▼──┐  ┌──▼──────────┐
 │  backend   │  │  frontend   │
 │  FastAPI + │  │  nginx +    │
 │  SegFormer │  │  CRA bundle │
 │  (:8001)   │  │  (:3000)    │
 └─────┬──────┘  └─────────────┘
       │
       ▼ mongodb+srv
 ┌─────────────────────┐
 │  MongoDB Atlas (M0) │
 └─────────────────────┘
```

---

## 1 · Get a server

**Recommended**: Hetzner Cloud [**CX22**](https://www.hetzner.com/cloud)
— 2 vCPU / 4 GB RAM / 40 GB NVMe / ~€4.50 per month. That leaves ~2 GB
headroom after the backend, which comfortably covers SegFormer's peak
usage (~1.4 GB during warm-up).

Any provider with **≥ 4 GB RAM and ≥ 20 GB disk** works (DO Droplet
`s-2vcpu-4gb`, Vultr "Cloud Compute 4 GB", Oracle ARM free tier, etc.).

1. Create the server with **Ubuntu 24.04** and your SSH key uploaded.
2. Note the public **IPv4** — you'll point DNS at it in step 3.
3. SSH in: `ssh root@<IP>`.

---

## 2 · Install Docker on the server

```bash
# One-liner installer from Docker (works on Ubuntu 24.04)
curl -fsSL https://get.docker.com | sh

# Enable & start
systemctl enable --now docker

# Verify
docker compose version
```

Create a non-root deploy user (optional but good hygiene):

```bash
adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
```

From now on run everything as `deploy` (or keep using `root`; both work).

---

## 3 · DNS

Point your domain's **A record** to the VPS IPv4.
If you also want `www`, add a second A record (or a CNAME → `dressapp.co`).

Propagation: usually < 5 minutes with Cloudflare, up to 1 hour elsewhere.
Verify with `dig +short dressapp.co @1.1.1.1`.

---

## 4 · Set up MongoDB Atlas (free M0 tier)

1. Sign up / log in at <https://cloud.mongodb.com>.
2. **Build a database → M0 (free)** → pick a region close to Hetzner
   (`eu-central-1` / Frankfurt pairs well with Hetzner Nuremberg).
3. **Database Access** → Add new user → password auth → save password.
4. **Network Access** → Add IP → start with `0.0.0.0/0` while you
   iterate; once the stack is healthy, replace with your VPS IP only.
5. **Connect → Drivers → Python** → copy the URI. It looks like:

   ```
   mongodb+srv://USER:<password>@CLUSTER.mongodb.net/?retryWrites=true&w=majority&appName=DressApp
   ```

   Replace `<password>`. You'll paste this into `deploy/.env`.

---

## 5 · Pull the code onto the server

```bash
cd /srv
git clone https://github.com/YOUR_ORG/dressapp.git
cd dressapp
```

(Alternatively use `scp` / `rsync` if you haven't pushed to a remote yet.)

---

## 6 · Create `deploy/.env`

```bash
cd /srv/dressapp
cp deploy/.env.example deploy/.env
$EDITOR deploy/.env   # fill in the values
```

**Minimum fields you MUST change before first boot:**

| Key | Where to get it |
|---|---|
| `DOMAIN` | Your domain (`dressapp.co`) |
| `CADDY_ACME_EMAIL` | Any valid email for Let's Encrypt notices |
| `MONGO_URL` | From Atlas (step 4) |
| `DB_NAME` | Pick a name, e.g. `dressapp_prod` |
| `JWT_SECRET` | `openssl rand -hex 48` (alphanumeric only is safest) |
| `EMERGENT_LLM_KEY` | Your Emergent universal key |
| `PAYPAL_LIVE_CLIENT_ID` / `_SECRET` / `_WEBHOOK_ID` | From the PayPal developer dashboard (LIVE credentials) |
| `PAYPAL_ENV` | `live` for production |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` | Google Cloud Console — the Web client whose **Authorized redirect URIs** include `https://YOUR_DOMAIN/api/v1/auth/google/callback` (and the `www` variant) |
| `GROQ_API_KEY` / `DEEPGRAM_API_KEY` / `OPENWEATHER_API_KEY` | Respective provider dashboards |
| `HF_TOKEN` | HuggingFace (only required if you re-enable HF segmentation) |

⚠️ **Quoting**: do **not** wrap values in `"..."` quotes. Docker Compose passes the literal quotes into the container as part of the value.

⚠️ **MongoDB URI sanity-check**: every parameter after `?` must be `key=value`. A trailing orphan like `&appName` (no `=`) will crash pymongo on startup.

Leave `GOOGLE_OAUTH_REDIRECT_URI` and `GOOGLE_OAUTH_POST_LOGIN_REDIRECT`
**empty** — the backend now derives them from the incoming request
host, which keeps the config working on preview, staging, prod, and any
custom domain.

---

## 7 · First build & launch

```bash
cd /srv/dressapp
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
```

First-time build takes **~8–12 minutes** (CPU-only torch is ~200 MB
download; CRA build ~2 min). Subsequent rebuilds use Docker cache and
finish in < 1 minute.

Watch progress:

```bash
docker compose -f deploy/docker-compose.yml logs -f
```

You should see, in order:

```
caddy     | serving initial configuration
caddy     | certificate obtained successfully
backend   | Uvicorn running on http://0.0.0.0:8001
frontend  | nginx started
```

Open `https://dressapp.co` — you should hit the login screen.

---

## 8 · Post-launch wiring

### 8.1 Google OAuth redirect URI

Go to [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
→ open your OAuth 2.0 Client → **Authorized redirect URIs** → add:

```
https://dressapp.co/api/v1/auth/google/callback
```

(Also add the preview URL if you still want to log in to the dev pod.)

### 8.2 PayPal webhook

In the PayPal developer dashboard, set the webhook URL to:

```
https://dressapp.co/api/v1/paypal/webhook
```

Copy the new `PAYPAL_WEBHOOK_ID` into `deploy/.env`, then
`docker compose -f deploy/docker-compose.yml up -d` to reload.

### 8.3 First-request model warm-up

The first call to `POST /api/v1/closet/analyze` downloads ~185 MB of
model weights (SegFormer b3 clothes + u2netp). This takes 20–30 s the
first time and is cached on the `model-cache` / `rembg-cache` volumes
so subsequent requests are 3–5 s.

If you want to warm it at deploy time (no user-facing cold start):

```bash
docker compose exec backend curl -sS -o /dev/null \
  -X POST http://127.0.0.1:8001/api/v1/closet/warm \
  || true  # endpoint is optional; ignore 404
```

(You can also just hit `/analyze` once yourself after deploying.)

---

## 9 · Day-2 operations

### View logs
```bash
docker compose -f deploy/docker-compose.yml logs -f backend
docker compose -f deploy/docker-compose.yml logs -f caddy
```

### Redeploy after code changes
```bash
cd /srv/dressapp
git pull
docker compose -f deploy/docker-compose.yml --env-file deploy/.env \
  up -d --build
```

### Free disk of old images
```bash
docker image prune -f
```

### Reset model cache (if you swap to a different SegFormer model)
```bash
docker compose -f deploy/docker-compose.yml down
docker volume rm dressapp_model-cache dressapp_rembg-cache
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d
```

### Scaling up
A single CX22 supports ~20 concurrent users comfortably. To handle more:

1. **Add a second backend instance**: duplicate the `backend` service
   in `docker-compose.yml` and put a `load_balancing_policy` in the
   Caddy `handle_path /api/*` block. Share the model cache volume.
2. **Move to CX32** (4 vCPU / 8 GB / ~€8/mo) — smaller change, more
   headroom for heavy outfits.
3. **Deploy `/app/inference-server/` on its own GPU box** and set
   `CLOTHING_PARSER_ENDPOINT_URL` + `BACKGROUND_MATTING_ENDPOINT_URL`
   — the backend will offload inference automatically.

---

## 10 · Backup strategy

MongoDB Atlas M0 includes **continuous automated backups** with a
24 h retention window (upgrade to M10 for point-in-time restore).
No backend-side action required.

For the model-cache volumes: they're pure caches — deleting them just
triggers a one-time re-download on the next request.

For Caddy certs: they live in `caddy-data` volume and are automatically
renewed. If the volume is lost, Caddy will re-obtain certs on next boot
(there's a per-week rate limit with Let's Encrypt — 50 certs/week/domain
is plenty for most recoveries).

---

## 11 · Troubleshooting

| Symptom | Check |
|---|---|
| Caddy "certificate_obtain_failed" | DNS hasn't propagated yet, or ports 80/443 are blocked by a firewall. Run `curl ifconfig.me` on the VPS, `dig +short dressapp.co @1.1.1.1`, compare. |
| Backend OOM (container restarts) | Instance has < 4 GB RAM. Add 4 GB swap (`fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab`), or upgrade, or set `USE_LOCAL_CLOTHING_PARSER=false` + `AUTO_MATTE_CROPS=false` in `deploy/.env` to disable the heavy vision models. |
| `/api/v1/closet/analyze` 500s | `docker compose logs backend`. Most common: missing `EMERGENT_LLM_KEY` or `MONGO_URL` in `.env`. |
| `pymongo.errors.InvalidURI: MongoDB URI options are key=value pairs.` | `MONGO_URL` has a malformed query parameter (e.g. trailing `&appName` with no `=value`). Fix in `.env` and `docker compose up -d --force-recreate backend`. |
| `pymongo.errors.OperationFailure: bad auth` | Wrong username/password in `MONGO_URL`. Reset the user's password in Atlas → Database Access. |
| Mongo connection timeout | Atlas → **Network Access** must include either `0.0.0.0/0` or this VPS's public IP. Get the IP with `curl -4 ifconfig.me`. |
| Google OAuth "redirect_uri_mismatch" | The OAuth Client whose ID is in `.env` must have your exact callback URL registered. If you have multiple OAuth clients in the project, double-check you're editing the right one — the URL bar of Google Console reveals the active client ID. |
| PayPal webhook 401 | Webhook ID in `.env` doesn't match what PayPal is signing requests with. Copy the correct ID from the PayPal dashboard. |
| First `/analyze` takes 30 s | Model warm-up (expected only once per server lifetime, thanks to the cache volume). |
| Browser shows `ERR_BLOCKED_BY_CLIENT` for some API calls | An ad blocker is blocking the URL because it contains `/ads/`. The promotion ticker uses `/promotions/` (renamed in this repo); if you fork older code, rename `/api/v1/ads/*` accordingly. |
| `pip install` fails on `emergentintegrations==0.1.0` | The Dockerfile must include `--extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/`. Already configured here. |
| `pip` resolver fails on protobuf / grpcio conflicts | The Dockerfile uses `--use-deprecated=legacy-resolver` to match the dev environment exactly. Already configured. |
| `docker: unknown command: docker compose` | Ubuntu's `docker.io` package omits the compose plugin. Install it manually: `mkdir -p /usr/local/lib/docker/cli-plugins && curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose && chmod +x /usr/local/lib/docker/cli-plugins/docker-compose`. |
