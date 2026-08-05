> ⚠️ **SUPERSEDED — retired v1 palette. Do not build against this file.**
> This is the indigo-era brand kit, kept as a record of what was fed to the
> brand-kit generator. The live design system is teal and lives in
> [`docs/frontend-brandkit.md`](../../docs/frontend-brandkit.md); the v2
> rationale is in [`../brandkit/frontend-brandkit-v2.md`](../brandkit/frontend-brandkit-v2.md).

# Yanki — Frontend Brand Kit

*Audience: the frontend junior (there is no designer on call). This is the design
system: copy these tokens into `frontend/tailwind.config.ts` and build the five
components against them. When in doubt, prefer boring and consistent over clever.*

See also: [architecture.md](architecture.md) (the API these components render),
[mvp.md](mvp.md) (the two screens they live on).

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
| `primary` (`bg-primary`, `text-primary`) | Brand accent: buttons, links, active step, gauge mid-band | `#4f46e5` (indigo-600) |
| `primary-50 … primary-900` | Indigo tint scale — e.g. `bg-primary-100` + `text-primary-700` badges, `hover:bg-primary-700`, `ring-primary-300` | `#eef2ff … #312e81` |
| `surface` | Card / panel background (`bg-surface`; components also use `bg-white`) | `#ffffff` |
| `surface-muted` | Page + inset backgrounds (`bg-surface-muted`) | `#f8fafc` (slate-50) |
| `surface-border` | Hairlines, dividers, input borders | `#e2e8f0` (slate-200) |
| `surface-foreground` | Primary text (`text-surface-foreground`) | `#0f172a` (slate-900) |
| `surface-subtle` | Secondary text, labels, captions | `#64748b` (slate-500) |
| `success` / `success-soft` | Footprint = yes, healthy score, deploy ok | `#16a34a` / `#dcfce7` |
| `success-700` (`text-success-700`) | Accessible green for text/glyphs sitting on a `success-soft` fill — `ResultsTable` "Yes" badge, `StepProgress` done check | `#15803d` |
| `danger` / `danger-soft` | Footprint = no, failed job, errors | `#dc2626` / `#fee2e2` |
| `danger-700` (`text-danger-700`) | Accessible red for text/headings sitting on a `danger-soft` fill — `ResultsTable` "No" badge, failure-card heading | `#b91c1c` |

Button text on `bg-primary` is `text-white` (there is no dedicated on-primary token).

The `-700` shades exist because the base hues fail small-text contrast on their own
`-soft` fills: `text-success` on `success-soft` is only **3.00:1** and `text-danger`
on `danger-soft` only **3.95:1** — both below the 4.5:1 floor. So for *any* text or
glyph on a `-soft` background, use `text-success-700` / `text-danger-700`. The base
`success` / `danger` remain correct for solid fills, borders, and the gauge arc.

**GEO score color scale** (drives `ScoreGauge`): 0–29% → `danger` (red), 30–59% →
`primary` (indigo), 60–100% → `success` (green). Never rely on color alone —
always pair with the numeric percentage and a label.

---

## 3. Typography

System font stack — zero web-font payload, fast first paint, matches the "boring
beats clever" ethos.

```
font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif
font-mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace   /* KYC JSON, snippets */
```

| Step | Tailwind class | Size / line-height | Use |
|---|---|---|---|
| Display | `text-4xl font-bold` | 36 / 40 | Landing headline |
| H1 | `text-3xl font-semibold` | 30 / 36 | Page titles |
| H2 | `text-xl font-semibold` | 20 / 28 | Section headers (KYC, Prompts, Responses) |
| Body | `text-base` | 16 / 24 | Default |
| Small | `text-sm` | 14 / 20 | Table cells, captions |
| Micro | `text-xs font-medium` | 12 / 16 | Labels, badges, step numbers |
| Code | `text-sm font-mono` | 14 / 20 | KYC JSON, matched snippets |

---

## 4. Spacing, radius, shadow

- **Spacing scale:** Tailwind default (4px base). Reach for `2`, `3`, `4`, `6`,
  `8`, `12`. Page gutter `px-4` mobile / `px-8` desktop; max content width
  `max-w-4xl mx-auto`.
- **Radius:** `rounded-lg` (8px) for cards/inputs, `rounded-md` (6px) for buttons,
  `rounded-full` for badges and the gauge track.
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
- Each step: a number/check icon, a name, and a state — `done` (`success` check),
  `active` (`primary`, animated), `pending` (`surface-subtle`).
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
- Grouped or sortable by prompt/engine is nice-to-have. Zebra rows via
  `surface-muted`. Horizontally scrollable on mobile (`overflow-x-auto`) — the
  page body must never scroll sideways.
- Also render the KYC JSON (in a `font-mono` code block) and the list of generated
  prompts on this screen.

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

- **Contrast:** text ≥ 4.5:1, large text/UI ≥ 3:1, in **both** themes. Verified
  pairings: `text-success-700` / `text-danger-700` on their `-soft` fills measure
  **4.57:1** / **5.30:1**; form-control boundaries use `surface-subtle` `#64748b`
  (**4.76:1** vs white) to meet WCAG 1.4.11, while `surface-border` `#e2e8f0` is
  kept for decorative dividers and card outlines only (exempt from 1.4.11). The
  bare `text-success` / `text-danger` must **not** carry small text on a `-soft`
  fill (see §2).
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
