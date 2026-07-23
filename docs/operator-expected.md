# Operator Expected — everything only a human can do

*The single operator file. Maintained by the orchestrator; tick items as you
do them. Nothing here blocks local development — `make dev` + `make test`
work with zero keys and zero cost (DRY_RUN).*

Last updated: 2026-07-10, **session 13 FINAL close (after five operator
follow-ups, all shipped same day; last-good `d6514ee`, CI green).**
The build is done: plan **43/44 ≈ 98%** — the only remaining card is
**P5.11: your go-live**. Beyond the six build tasks, this session also
delivered on your directives: the **Gemini prod-incident hotfix**
(live-proven: 4 real engines, $0.0253/analysis), **brand icons + logo
site-wide**, **growth-loop emails** (thank-you invites a first analysis;
kind-aware run-alert links; waitlist CTA on both results pages), the
**responses-table width fix**, the **"yanki" wordmark spelling**, and —
with your verified domain + new key — **emails now DELIVER to real
recipients** (proven both directions). The checker still answers 503
(dark) until B3. Signup mails are deduped by design: one thank-you per
address ever, 10 signups/IP/hour (your question — session log §11).
Next session = P5.11 at your pace: answer A1, do B2, then B3.

## A. Questions waiting for your answer

*Reply in chat or edit inline. "Keep defaults" is a complete answer for A1.*

- [ ] **A1. Checker go-live decisions** (the former item 13; due before
  P5.11 flips the checker public):
  - **Abuse thresholds** — in code: 10 checks/IP/hour, 20 fresh
    runs/brand/day, $5/day cost cap. *Default: keep.* → Answer: ______
  - **Email-gate strength** — single unverified email (max lead capture)
    vs verification / disposable-domain blocking / captcha.
    *Default: single unverified.* → Answer: ______
  - **The one free raw answer** — *default: first answer that mentions the
    brand.* → Answer: ______

## B. Actions only you can do (in priority order)

- [x] **B1. Resend sending domain — DONE 2026-07-10** (you verified
  `beyondkaira.com` and supplied a new key + sender). Prod now sends as
  `Yanki <aytek@beyondkaira.com>` (new key in gitignored `deploy/.env`,
  redeployed same day). Live-proven: a fresh waitlist signup delivered the
  thank-you to the joiner and the alert to `info@beyondkaira.com` with no
  errors. If you'd rather send from a different mailbox (e.g.
  `yanki@beyondkaira.com`), change `EMAIL_FROM` in `deploy/.env` and
  redeploy — the domain is what's verified, not the mailbox.
- [ ] **B2. Vendor ToS + pricing check for Gemini/Perplexity** (before
  P5.11 go-live) — **updated after the 2026-07-10 prod incident** (a live
  analysis failed; fixed same day, commit `7ff580f`): Google retired
  `gemini-2.5-flash` for new accounts, so the adapter now uses the rolling
  alias **`gemini-flash-lite-latest`**, and your free-tier key has **zero
  search-grounding quota** — Gemini answers are honestly labeled
  `:ungrounded` until you act. Your parts:
  (a) **Enable billing on your Google AI Studio project** if you want
  grounded (live web search) Gemini answers — after enabling, just tell
  the next session to redeploy; grounding re-activates automatically.
  (b) Verify current prices: flash-lite is pinned **UNVERIFIED** at
  $0.10/$0.40 per 1M in/out; Perplexity `sonar` $1/$1 (verified working
  live). `cost_usd` still undercounts per-request search fees — retune in
  P5.11's week-1 read.
  (c) The ToS sanity check on both vendors stands.
- [ ] **B3. P5.11 go-live itself stays yours** (after A1 + B2): flip
  `CHECKER_ENABLED=1` in `deploy/.env`, redeploy, supervise the live
  4-engine smoke. No agent will flip it.
- [ ] **B4. Rotate the Resend API key when convenient** — BOTH keys you
  used today were pasted into chat transcripts (the original and the
  2026-07-10 replacement `re_6ZpH…`); rotate in the dashboard, re-paste
  into `deploy/.env`, redeploy.
- [ ] **B5. (Optional) local browser deps, one root command:**
  `cd frontend && sudo npx playwright install-deps chromium` — enables
  local `make e2e` + native screenshots. Fully skippable: CI proves the
  e2e on every push; screenshots are done via dockerized Chrome.

## C. Done (compacted history)

- [x] Session 13: **Gemini + Perplexity keys pasted** (closes the old
  item 12) → P5.7 shipped same session (`40d8a34`). **Brandkit v2 decision**
  (old item 14) → P5.12 shipped (`d5abee7`), WCAG ratios recorded,
  before/after screenshots in the session log.
- [x] Sessions 1–12: KYC fix verified · $10 spend caps on Anthropic+OpenAI
  (plus code-side caps; blast radius doubly bounded — escape hatches:
  `ANALYSES_DAILY_CAP=0` or `DRY_RUN=1` + redeploy) · run-mode LIVE
  (session 8) · OpenAI billing proven ($0.0026/analysis) · Caddyfile
  committed in ams-pulse (`d538631`) · first deploy + rollback exercised
  (P4.2) · real Anthropic/OpenAI keys (P4.1) · GitHub + CI green
  (`aytekXR/yanki-mvp`) · DNS `yanki.beyondkaira.com → 161.97.172.146` ·
  real `POSTGRES_PASSWORD` in `deploy/.env`.
- [x] Turkish: **deferred to Later, whole product EN-only** (your
  2026-07-10 directive; P5.8/P5.9 skipped, revive on your word).

## Local-machine quirks (informational)

- **Ports 5432 and 8140 are taken on this host.** Dev stack is
  parameterized: `YANKI_DB_PORT=5434 YANKI_WEB_PORT=8240 make dev`
  (web → http://localhost:8240, api on 8141). **Prod** loopback binds are
  8142 (web) / 8143 (api) — the host nginx edge proxies to these (they also
  serve deploy health checks).
- **Node is v20 here; README recommends 22 LTS.** All green on 20 —
  upgrade optional.
- **Docker group membership may not apply to long-lived sessions** —
  prefix with `sg docker -c "…"` or use a fresh login shell.
