# Yanki — Frontend Brand Kit

*Audience: the frontend junior (there is no designer on call). This is the design
system: copy these tokens into `frontend/tailwind.config.ts` and build the five
components against them. When in doubt, prefer boring and consistent over clever.*

**v2 supersedes v1 (2026-07-10, P5.12).** The visual identity is now the "echo"
system: deep petrol ink + echo teal, Sora + IBM Plex Mono. The source of truth is
[brandkit/brandkit/frontend-brandkit-v2.md](../brandkit/brandkit/frontend-brandkit-v2.md);
§2 and §3 below are reconciled to it. The indigo-based v1 palette is retired — no
doc or component quotes the dead indigo/slate hexes.

See also: [architecture.md](architecture.md) (the API these components render),
[02-mvp.md](02-mvp.md) (the two screens they live on).

---

## 1. Design principles

1. **Show your work.** The product's whole pitch is transparency, so the UI never
   hides data. Every score links to the raw answers behind it (Answers Explorer is
   roadmap, but `matched_snippet` is shown in the MVP `ResultsTable`).
2. **Calm, confident, technical.** This is a measurement tool, not a toy. Restrained
   color, generous whitespace, one accent.
3. **Tokens, not hexes.** Never hard-code a hex in a component — always use the
   Tailwind token (`bg-primary`, `text-surface-foreground`). A dark theme is a
   roadmap item; the tokens ship as single (light) values today.

---

## 2. Color palette

The token families below map to `theme.extend.colors` in
`frontend/tailwind.config.ts` — this table and that file must stay in sync. Use
the **class** name in markup (`bg-primary`, `text-danger`), never the raw hex.
Tokens are single (light) values today; a dark theme is a roadmap item.

| Token (class) | Role | Hex |
|---|---|---|
| `primary` | Brand accent: buttons, links, active step | `#0E7569` |
| `primary-hover` | Button hover, link hover | `#0A5B51` |
| `primary-soft` | Selected rows, soft badges, hero/chip pill | `#E2F3EF` |
| `primary-strong` | Accessible teal text/glyph on a `primary-soft` fill | `#0A5B51` |
| `signal` | Bright accent — **dark surfaces only** (charts, mark) | `#3BD1B5` |
| `ink` | Dark surfaces: KYC/code block, footer, marketing dark | `#0B1D26` |
| `ink-foreground` **(minted)** | Mono text/glyph on the `ink` surface | `#C7DBE0` |
| `surface` | Card / panel background (`bg-surface`; components also use `bg-white`) | `#FFFFFF` |
| `surface-muted` | Page + inset/header backgrounds | `#F5F8F8` |
| `surface-border` | Hairlines, dividers, card outlines (decorative only) | `#DCE6E9` |
| `surface-foreground` | Primary text | `#0C1E28` |
| `surface-subtle` | Secondary text, labels; form-control borders | `#4E6B78` |
| `surface-zebra` **(minted)** | `ResultsTable` alternating (zebra) rows | `#F9FBFB` |
| `success` / `success-soft` | Footprint = yes, score ≥ 60% | `#177E4D` / `#DDF3E4` |
| `success-strong` | "Yes" badge text, `StepProgress` done check on `-soft` | `#116038` |
| `warning` / `warning-soft` | Score 30–59% | `#B45309` / `#FCEFD8` |
| `warning-strong` | Warning badge text on `-soft` | `#8A4B08` |
| `danger` / `danger-soft` | Footprint = no, failed job, score 0–29% | `#C4403A` / `#FBE5E3` |
| `danger-strong` | "No" badge text, failure-card heading on `-soft` | `#9E332E` |

Button text on `bg-primary` is `text-white` (there is no dedicated on-primary token).

**Minted tokens.** The spec references two hexes without naming them: the zebra row
fill `#F9FBFB` and the KYC-on-ink code text `#C7DBE0`. They are minted here as
`surface-zebra` and `ink-foreground` so components stay hex-free.

The `-strong` shades exist because each base hue fails small-text contrast on its own
`-soft` fill (below the 4.5:1 floor). So for *any* text or glyph on a `-soft`
background, use the `-strong` shade; `signal` `#3BD1B5` fails on white and is
**dark-surface only**. The base `success` / `warning` / `danger` remain correct for
solid fills, borders, and the gauge arc.

**GEO score bands** (drives `ScoreGauge`): 0–29% → `danger`, 30–59% → `warning`
(v1 used `primary` here; v2 makes the mid band semantic), 60–100% → `success`.
Never rely on color alone — always pair with the numeric percentage and a label.

**Measured WCAG 2.x contrast ratios** (recomputed against the *implemented*
combinations; debt #13 — axe cannot check contrast under jsdom). Normal text needs
≥ 4.5:1; graphical/large UI ≥ 3:1. Every implemented pair passes.

| Text / mark | On fill | Ratio | Floor |
|---|---|---|---|
| `primary-strong` | `primary-soft` (chips, step circle) | 6.96:1 | 4.5 |
| `success-strong` | `success-soft` (Yes badge, done check) | 6.54:1 | 4.5 |
| `danger-strong` | `danger-soft` (No badge) | 5.87:1 | 4.5 |
| `warning-strong` | `warning-soft` (warning badge) | 5.98:1 | 4.5 |
| `primary` | white (links, ghost, toggle) | 5.57:1 | 4.5 |
| `primary-hover` | white (link hover) | 7.99:1 | 4.5 |
| white | `primary` (button text, active step number) | 5.57:1 | 4.5 |
| `surface-subtle` | white (captions, model column) | 5.68:1 | 4.5 |
| `surface-subtle` | `surface-muted` (table header) | 5.32:1 | 4.5 |
| `surface-subtle` | `surface-zebra` (model column, zebra row) | 5.47:1 | 4.5 |
| `surface-foreground` | white | 17.05:1 | 4.5 |
| `surface-foreground` | `surface-muted` (page bg) | 15.96:1 | 4.5 |
| `surface-foreground` | `surface-zebra` (table cell) | 16.41:1 | 4.5 |
| `ink-foreground` | `ink` (KYC/code mono text) | 12.02:1 | 4.5 |
| `danger` arc | white (gauge 0–29 band) | 5.07:1 | 3.0 |
| `warning` arc | white (gauge 30–59 band) | 5.02:1 | 3.0 |
| `success` arc | white (gauge 60–100 band) | 5.09:1 | 3.0 |

The `ink-foreground` pair measures 12.02:1 (spec quoted a conservative 7.9:1); both
clear the floor. No new hexes were invented to reach compliance.

---

## 3. Typography

Two webfonts, **self-hosted by `next/font/google`** at build (no runtime CDN, no
`<link>` tags): Sora 300/400/500/600 and IBM Plex Mono 400/500, `display=swap`.
Wired to CSS variables (`--font-sans`, `--font-mono`) consumed by tailwind
`fontFamily`. Mono is the "evidence" voice: KYC JSON, snippets, scores, ids.

```
font-sans: 'Sora', ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif
font-mono: 'IBM Plex Mono', ui-monospace, "SF Mono", Menlo, Consolas, monospace
```

| Step | Tailwind class | Size / line-height | Use |
|---|---|---|---|
| Display | `text-5xl font-semibold tracking-tight` | 48 / 1.15 | Landing headline |
| H1 | `text-3xl font-semibold tracking-tight` | 30 / 1.2 | Page titles |
| H2 | `text-xl font-semibold` | 20 / 1.4 | Section headers (KYC, Prompts, Responses) |
| Body | `text-base` | 16 / 1.5 | Default |
| Small | `text-sm` | 14 / 1.45 | Table cells, captions |
| Micro | `text-xs font-medium uppercase tracking-wider` | 12 / 1.35 | Labels, step labels |
| Code | `text-sm font-mono` | 14 / 1.5 | KYC JSON, matched snippets |

---

## 4. Spacing, radius, shadow

- **Spacing scale:** Tailwind default (4px base). Reach for `2`, `3`, `4`, `6`,
  `8`, `12`. Page gutter `px-4` mobile / `px-8` desktop; max content width
  `max-w-4xl mx-auto`.
- **Radius (v2):** `rounded-xl` (12px) cards/panels, `rounded-lg` (8px)
  inputs/insets, `rounded-md` (6px) buttons, `rounded-full` badges and gauge track.
- **Shadow:** `shadow-sm` on raised cards; avoid heavy shadows in dark mode (use
  `surface-border` instead).
- **Grid rhythm:** vertical space between sections `space-y-8`; within a card
  `space-y-4`.

---

## 5. Component specs

All five ship as **real, styled** components using the tokens above. Content is
driven entirely by the API response — no hard-coded copy in the data path.

### `Button`
- Variants: `primary` (`bg-primary text-white`), `secondary`
  (`bg-white border border-surface-border text-surface-foreground`), `ghost`
  (text only). Sizes `sm`/`md`.
- States: hover (slightly darker/lighter), `focus-visible:ring-2 ring-primary`,
  `disabled:opacity-50 cursor-not-allowed`, and a `loading` state (spinner +
  `aria-busy`, button disabled).
- Always a real `<button>` with a discernible label.

### `UrlForm` (Screen 1)
- A single URL `<input type="url">` + a primary submit Button.
- Client-side validation: non-empty, looks like a URL; show an inline `danger`
  message under the field (never an alert box).
- On submit: disable the button + show loading, `POST /api/v1/analyses` via
  `lib/api.ts`, then `router.push('/analyses/{id}')`. On API error, re-enable and
  show the message.
- The `<input>` has an associated `<label>` (visually hidden is fine).

### `StepProgress` (Screen 2)
- Renders the 6 pipeline steps: discovery → KYC → prompts → executing → footprint
  → scoring. Maps from `status` + `progress`.
- Each step: a number/check icon, a name, and a state — `done`
  (`success-soft` circle + `success-strong` check), `active` (solid `primary`
  circle, white number, `motion-safe` box-shadow pulse-ring), `pending`
  (`surface-subtle`).
- A thin overall progress bar (`bg-primary`, width = `progress`%). Include
  `role="progressbar"` with `aria-valuenow`.

### `ScoreGauge` (Screen 3)
- A radial/arc gauge showing the GEO score 0–100%. Arc color from the score scale
  (§2). Big numeric percentage in the center (`text-4xl font-bold`), a
  `surface-subtle` caption ("GEO score — X of Y responses mentioned you").
- Accessible: `role="img"` with an `aria-label` stating the score in words. Never
  color-only.

### `ResultsTable` (Screen 3)
- One row per `response`: columns = Engine, Model, Footprint (a `success`/`danger`
  badge with text "Yes"/"No", not just a color), Matched snippet (`font-mono`,
  truncated with a title/expand), and (optionally) the prompt it answered.
- Footprint badges: "Yes" on `success-soft`/`success-strong`, "No" on
  `danger-soft`/`danger-strong`. Zebra rows via `surface-zebra` (alternating
  with white). Horizontally scrollable on mobile (`overflow-x-auto`) — the page
  body must never scroll sideways.
- The KYC profile (`KycCard`) and the list of generated prompts also render on
  this screen. Per spec §5 the `KycCard` block renders on the `ink` surface
  (`bg-ink`) with `ink-foreground` (`#C7DBE0`) `font-mono` evidence text. The
  structured labels, value rows, and chip list (roles, copy, test ids) are
  preserved as a token substitution, not a raw JSON dump.

### Failure state
- On `status=failed`, show a `danger`-bordered card with the `error` text and a
  "try another URL" link. Do not blank the screen.

---

## 6. Voice & tone

**Personality:** the knowledgeable, honest analyst. Plain, specific, never hypey.
We *show* numbers instead of *claiming* results.

- Prefer specifics: "You appear in 9 of 20 answers" > "Great visibility!"
- Own the limits: this is a primitive score; say so where relevant.
- No dark patterns, no fake urgency.

### English (launch)

| Context | Copy |
|---|---|
| Landing headline | "See how AI answers talk about your brand." |
| URL field placeholder | "https://your-company.com" |
| Submit button | "Run analysis" |
| Progress | "Analyzing… this takes a few minutes." |
| Score caption | "GEO score — mentioned in {n} of {total} answers." |
| Empty footprint | "Not mentioned in this answer." |
| Failure | "We couldn't finish this analysis. {reason} Try another URL." |

### Turkish (roadmap — native, NOT translated)

Turkish is a Near-phase feature ([roadmap.md](roadmap.md)); it must be **written
natively**, not machine-translated, because getting Turkish wrong kills the
differentiation story. Reference tone below; a native speaker signs off before ship.

| Context | Copy |
|---|---|
| Landing headline | "Yapay zeka yanıtları markanızdan nasıl bahsediyor, görün." |
| Submit button | "Analizi başlat" |
| Progress | "Analiz ediliyor… birkaç dakika sürebilir." |
| Score caption | "GEO puanı — {total} yanıtın {n} tanesinde bahsedildi." |
| Failure | "Analiz tamamlanamadı. {reason} Başka bir adres deneyin." |

Turkish brand matching must handle suffixes (e.g. *Marka'nın*, *Markayı*) — a
`# TODO(pipeline)` on `footprint.py`, gated on a labeled Turkish test set.

---

## 7. Accessibility baselines

Non-negotiable, checked in review:

- **Contrast:** text ≥ 4.5:1, large text/UI ≥ 3:1. Verified pairings are the §2
  measured table: the `-strong` shades on their `-soft` fills all clear 4.5:1
  (`success-strong` 6.54:1, `danger-strong` 5.87:1, `warning-strong` 5.98:1,
  `primary-strong` 6.96:1); form-control boundaries use `surface-subtle` `#4E6B78`
  (5.68:1 vs white) to meet WCAG 1.4.11, while `surface-border` `#DCE6E9` is kept
  for decorative dividers and card outlines only (exempt from 1.4.11). The bare
  `success` / `warning` / `danger` must **not** carry small text on a `-soft` fill
  (see §2).
- **Never color-only:** footprint yes/no, score bands, and step states always carry
  text or an icon in addition to color.
- **Keyboard:** every interactive element is focusable with a visible
  `focus-visible` ring; logical tab order; the form submits on Enter.
- **Semantics + ARIA:** real `<button>`/`<label>`/`<table>`; `role="progressbar"`
  on the bar, `role="img"` + `aria-label` on the gauge, `aria-busy` on loading,
  `aria-live="polite"` on the status region so screen readers hear progress updates.
- **Motion:** honor `prefers-reduced-motion` for the animated step + gauge.
- **Target size:** interactive targets ≥ 40×40px.

This checklist is now *partially* enforced by automated tests: the
`frontend/tests/*.a11y.test.tsx` suites run `axe-core` over each component and catch
missing roles, names, labels, and ARIA. Contrast is the exception — jsdom does no
layout or paint, so axe's `color-contrast` rule is disabled in the shared
`tests/a11y.ts` helper; the ratios above are verified by computed values instead.
