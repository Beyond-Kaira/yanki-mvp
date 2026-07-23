# Yanki — Caddy → host-nginx edge migration

> **Status: COMPLETE (2026-07).** The cutover has been executed: host nginx
> (`deploy/nginx/yanki.beyondkaira.com.conf`, TLS via certbot HTTP-01 webroot)
> is the live edge, proxying to the loopback binds 127.0.0.1:8142 (web) /
> 127.0.0.1:8143 (api). The retired Caddy block (`deploy/caddy/`) has been
> deleted from the repo. This document is retained as the executed runbook.

Move `yanki.beyondkaira.com` off the **shared containerised Caddy** and onto
**host nginx** with **wildcard TLS** and **private-loopback** upstreams. Every
artifact here is **additive** — the existing Caddy block, `deploy.sh`,
`rollback.sh` and `docker-compose.prod.yml` are untouched and keep serving until
you run the cutover, which is **reversible**.

- **Host:** `161.97.172.146` = `beyondkaira.com`, user `aytek`, Docker + systemd.
- 👤 = owner step, needs `sudo`.  🤖 = committed artifact / no-sudo, already done.
- Legend for "the risky one": the :443 cutover (§4) is the only step that can
  affect the OTHER live sites; it is windowed and has a one-command rollback.

---

## What changes, and what does NOT

| | Caddy (before) | nginx (now) |
|---|---|---|
| Edge | shared **container** `pulse-prod-caddy-1`, one hand-edited Caddyfile | host **nginx**, `deploy/nginx/yanki.beyondkaira.com.conf`, one file |
| TLS | terminated on the shared Caddy | wildcard `*.beyondkaira.com` cert on nginx |
| Upstream to api | `reverse_proxy yanki-api:8141` (docker network **alias**) | `127.0.0.1:8143` (private host loopback) |
| Upstream to web | `reverse_proxy yanki-web:8140` (docker network **alias**) | `127.0.0.1:8142` (private host loopback) |
| Routing | `@api path /api/* /healthz` → api, else → web | `location /api/` + `location = /healthz` → api, `location /` → web |
| Container binds | unchanged | **unchanged** |
| Deploy | `deploy/deploy.sh` (health = loopback) | `deploy/deployment.sh` (health = public url) |

**The key insight — no container bind change is needed.** The shared Caddy is a
*container*, so it could only reach the app over docker network aliases
(`yanki-api` / `yanki-web`) and the containers had to publish onto that network.
Host nginx runs on the *host*, so it reaches the app over the `127.0.0.1` ports
`docker-compose.prod.yml` **already publishes**:

```
api:  ports: - "127.0.0.1:${YANKI_PROD_API_PORT:-8143}:8141"
web:  ports: - "127.0.0.1:${YANKI_PROD_WEB_PORT:-8142}:8140"
```

Compose already calls these binds "ONLY for deploy.sh health checks and local
debugging". The migration promotes them from a debug aid to the real upstream.
They are `127.0.0.1`-only, so nothing on them is internet-reachable — exactly the
security fix the new model wants, achieved with **zero edits** to compose.

### Caddy block → nginx block, line by line

```
# deploy/caddy/yanki.beyondkaira.com.caddy        deploy/nginx/yanki.beyondkaira.com.conf
yanki.beyondkaira.com { ............................ server { listen 443 ssl; server_name yanki.beyondkaira.com; }
  @api path /api/* /healthz ......................... location /api/ { ... }  +  location = /healthz { ... }
  handle @api { reverse_proxy yanki-api:8141 } ...... proxy_pass http://yanki_api;  (upstream 127.0.0.1:8143)
  handle { reverse_proxy yanki-web:8140 } ........... location / { proxy_pass http://yanki_web; }  (127.0.0.1:8142)
}
# (Caddy auto-TLS + auto HTTP→HTTPS) ............... server { listen 80; return 301 https://... }  +  wildcard cert refs
```

`path /api/*` matches `/api/` and everything under it (bare `/api` falls through
to web); `location /api/` (prefix) + `location /` reproduce that split exactly.
`/healthz` is an exact match in both.

### Run model — why no systemd unit is added

Yanki's run model is **docker-compose** (`restart: unless-stopped` already
supervises the containers across reboots). That is unchanged, so no systemd unit
is introduced. The migration artifacts are just the nginx block and the
nginx-aware `deployment.sh`. Supervision stays with compose; nginx only replaces
the edge.

---

## 0. 👤 Prerequisites (once per host — shared with every other subdomain)

These are host-wide and set up once for all sites (see the blueprint
`deploy/INSTALL.md`). Verify they exist before touching Yanki:

```bash
# nginx installed and running
systemctl is-active nginx
# wildcard cert present (covers yanki.beyondkaira.com with no per-site step)
sudo ls -l /etc/letsencrypt/live/beyondkaira.com/fullchain.pem
# DNS resolves to this host (an A record for yanki, or the wildcard *.beyondkaira.com)
dig @8.8.8.8 +short yanki.beyondkaira.com   # -> 161.97.172.146
```

If any is missing, do the host-wide steps 1–2 of the blueprint `deploy/INSTALL.md`
first. Do NOT issue a per-subdomain cert — the wildcard already covers Yanki.

## 1. 👤 Install the nginx site (does NOT touch :443 yet)

Adding the file and reloading nginx is safe: nginx keeps serving whatever it
already serves, and this new `server` block only activates once nginx owns
`:443` (step 4). Until then Caddy is still the edge.

```bash
cd ~/repo/yanki-mvp     # or wherever this repo is checked out on the host
sudo cp deploy/nginx/yanki.beyondkaira.com.conf \
    /etc/nginx/sites-available/yanki.beyondkaira.com.conf
sudo ln -sfn /etc/nginx/sites-available/yanki.beyondkaira.com.conf \
    /etc/nginx/sites-enabled/yanki.beyondkaira.com.conf
sudo nginx -t          # a bad config is rejected here, never served
sudo systemctl reload nginx
```

## 2. 🤖 Confirm the private upstreams are up

The app must already be running (via `deploy/deploy.sh` or
`deploy/deployment.sh`) so the loopback ports answer. No change to compose is
needed — just verify:

```bash
curl -fsS http://127.0.0.1:8143/healthz   # api  -> {"status":"ok"}
curl -fsS http://127.0.0.1:8142/ | head   # web  -> Next.js HTML
```

If you run non-default ports, set `YANKI_PROD_API_PORT` / `YANKI_PROD_WEB_PORT`
in `deploy/.env` AND update the two `upstream` ports in the nginx conf to match,
then `sudo nginx -t && sudo systemctl reload nginx`.

## 3. 👤 Rehearse the edge BEFORE cutover (optional but recommended)

Prove the nginx block routes correctly while Caddy still owns real `:443`, by
resolving the hostname to loopback for one curl (this hits nginx on the host):

```bash
# Only works after nginx owns :443 (step 4). To test the block earlier, add a
# temporary second listen (e.g. 127.0.0.1:8443 ssl) — out of scope here.
curl -fsS --resolve yanki.beyondkaira.com:443:161.97.172.146 \
     https://yanki.beyondkaira.com/healthz    # -> {"status":"ok"}
```

## 4. 👤 The Caddy → nginx :443 cutover (the one risky, reversible step)

nginx and Caddy cannot both own `:443`. Do this in a maintenance window. Because
the shared Caddy also terminates TLS for the OTHER sites (pulse-prod, Ant Media,
brier), the clean move is to have nginx blocks for **every** current Caddy site
ready first (strangler); this document covers only Yanki's block.

```bash
# Cutover — free :443 from Caddy, hand it to nginx:
sudo docker stop pulse-prod-caddy-1        # frees :443 (stops ALL Caddy sites)
sudo systemctl reload nginx                # nginx now answers :443 for yanki
curl -fsS https://yanki.beyondkaira.com/healthz    # -> {"status":"ok"}
```

**Rollback (reverses the cutover in seconds):**

```bash
sudo systemctl stop nginx                  # (or remove yanki's :443 listen)
sudo docker start pulse-prod-caddy-1       # Caddy back on :443, unchanged
```

The Caddy block (`deploy/caddy/yanki.beyondkaira.com.caddy`) was kept in the
repo until the site was proven on nginx, then deleted (see the status note at
the top).

## 5. 🤖 Deploy from now on

After cutover, use the nginx-aware deploy driver — it health-checks the PUBLIC
url, so a green run proves the whole nginx path-split serves:

```bash
deploy/deployment.sh --check    # preflight + validate compose, change nothing
deploy/deployment.sh            # build -> up -> public health -> record .last-good
```

Pre-cutover, `deploy/deploy.sh` remains the deploy path (loopback health check),
or run `deployment.sh` with `HEALTH_URL=http://127.0.0.1:8143/healthz`.

Rollback discipline is preserved end to end: `.last-good` records the known-good
short SHA, `rollback.sh` redeploys it, and `deployment.sh`'s every failure path
is `if ! <step>; then rollback; fi` (a bare failing command under `set -e` would
skip the rollback — the core lesson from `deploy.sh`).

---

## Environment keys

Secrets live in `deploy/.env` (gitignored; never committed). The tracked
template `deploy/.env.example` documents every app key. This migration adds NO
required key — the app config is unchanged. `deployment.sh` reads a few OPTIONAL
tuning vars, all with safe defaults (set them in `deploy/.env` only to override):

| Key | Default | Purpose |
|---|---|---|
| `HEALTH_URL` | `https://yanki.beyondkaira.com/healthz` | public url the deploy health-gates against |
| `HEALTH_EXPECT` | `ok` | substring the health body must contain |
| `HEALTH_KEY` | `status` | second substring the health body must contain |
| `HEALTH_TRIES` | `45` | curl attempts, 2s apart (covers `alembic upgrade head`) |
| `HEALTH_CURL_OPTS` | *(empty)* | extra curl args, e.g. `--resolve yanki.beyondkaira.com:443:161.97.172.146` |
| `DEPLOY_ALLOW_DIRTY` | `0` | `1` skips the clean-tree guard (rehearsal only) |
| `YANKI_PROD_API_PORT` | `8143` | host loopback port for api (must match the nginx `yanki_api` upstream) |
| `YANKI_PROD_WEB_PORT` | `8142` | host loopback port for web (must match the nginx `yanki_web` upstream) |

Never put a secret value in a tracked file, this runbook included.
