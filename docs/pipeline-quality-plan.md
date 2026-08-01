# From MVP to product — input quality (discovery → KYC → prompts)

*Audience: pipeline engineers + the operator. This is the improvement plan for
the three steps that decide whether the GEO number means anything:
**discovery**, **KYC extraction**, and **prompt generation**. It is the
successor to [`discovery-kyc-improvements.md`](discovery-kyc-improvements.md)
(steps 1, 2a, 3, 4, 5 of which shipped 2026-07-28) and it stays inside the
current, operator-approved, English-only scope.*

**Status: workstreams D, K and P are implemented on
`feat/pipeline-quality-production-grade`.** Each section below carries a
`Shipped` note recording what actually landed and every deviation from the
proposal. §7 lists what was deliberately *not* built and why.

---

## 1. Why this plan exists

The MVP proved the loop: URL in, GEO score out. What it did not prove is that
the number is **about the right company, asked with the right questions**. Those
two properties are decided entirely in the first three steps, and none of them
fails loudly:

| Step | Failure mode | What the user sees |
|---|---|---|
| discovery | crawls a login page, a cookie banner and six copies of the footer | a confident score |
| kyc | invents a product line, or names a competitor that isn't on the site | a confident score |
| prompts | asks "Who are the leading **payload capacity** manufacturers?" | a confident score |

That last one is not hypothetical. It is the real KYC of `beyondtech.com.tr`
(analysis `58913428`), pinned as a fixture in `test_prompts.py`: the model
returned `keywords = [..., "EW immune", "anti-armor", "RPG-7 capability",
"payload capacity", "flight endurance", ...]`. Those are *spec attributes*, and
the template layer happily conjugates them into questions no human has ever
asked. Every such prompt is 4 paid engine calls spent measuring nothing.

**The MVP treated these three steps as plumbing. A product treats them as the
measurement instrument.** The distinction this plan is built on:

> A production-grade pipeline does not just produce output — it knows which of
> its outputs it is **entitled to believe**, and refuses to spend money on the
> rest.

Three principles follow, and each workstream below serves one:

1. **Fidelity** — what we send the model must be the site, not the site's
   chrome (workstream **D**).
2. **Groundedness** — what we persist as fact must be traceable to the crawl,
   never to the model's imagination (workstream **K**).
3. **Question realism** — what we ask engines must be what a buyer would ask,
   and must never contain the brand we are measuring (workstream **P**).

### Cost, stated up front

**No workstream here adds a single paid call.** The KYC step still makes exactly
one provider call on the happy path (one bounded retry on failure, unchanged).
Prompt generation stays deterministic and free. The plan buys quality by asking
the *existing* call for better fields and by spending more CPU on text we have
already paid to fetch — not by buying more inference. This is deliberate:
tech-debt #27 (KYC-stage spend is invisible to every cost control) is still
open, and no plan should widen an unmetered surface.

---

## 2. Workstream D — discovery: crawl fidelity

### D1 — decode pages with the encoding they declare

**Today.** `_fetch` returns `response.text`. httpx picks the charset from the
`Content-Type` header and, when the header carries none, defaults to UTF-8. A
page served as bare `text/html` but authored in ISO-8859-9 / windows-1254 (still
common on Turkish sites) therefore arrives as mojibake — and mojibake survives
every downstream step, because nothing after discovery knows what the bytes were
supposed to be.

**Change.** When the header declares no charset, look for `<meta charset>` /
`<meta http-equiv="Content-Type">` in the first 2 KB of the raw bytes and decode
with that, falling back to httpx's own guess. Header charset always wins — a
server that states its encoding is more authoritative than the document.

**Risk** low. Every respx fixture built with `html=` gets
`charset=utf-8` from httpx, so they take the header path unchanged.

**Proof.** A windows-1254 page with no header charset yields readable Turkish;
a header-declared charset is not overridden by a lying `<meta>`.

**Shipped as proposed.** `_decode` also caps decoding at `MAX_PAGE_BYTES` so the
size guard cannot be bypassed by a chunked response with no `content-length`.

### D2 — sniff binary payloads (closes tech-debt #28)

**Today.** `_is_html` fails open on a missing/empty Content-Type — a documented,
deliberate choice — so a header-less PDF still reaches BeautifulSoup, and its
mojibake eats the 20k-char budget real copy needed.

**Change.** Before parsing, sniff the first bytes for the magic numbers of the
formats a site actually links: `%PDF`, `PK\x03\x04` (zip/office), `\x89PNG`,
`GIF8`, JPEG `\xff\xd8\xff`, and a NUL byte in the first 512 (no text/html
begins with one). Skip those; keep failing open for everything else.

**Why this and not "stop failing open".** Fail-open on a *missing* header is
right — it matches `net_guard`'s stance and keeps offline dev working. What was
wrong is that we never looked at the bytes we already had in hand.

**Proof.** A header-less PDF link is skipped; a header-less HTML link still
parses (the existing test stays green, unchanged).

**Shipped as proposed.**

### D3 — retry the homepage once on a transport error

**Today.** One `httpx.HTTPError` on the homepage ends the job with "could not
read the site". A single reset connection or DNS blip costs the whole run — and
the user's only recovery is to submit again.

**Change.** Retry the homepage fetch **once** on a transport error. Same URL, no
backoff worth the name (the client already carries a 15s timeout), one extra
attempt.

**Deliberately not done: www/apex and scheme fallbacks.** They would issue
requests to URLs the caller never gave us, which (a) `follow_redirects=True`
already covers for the overwhelming majority of real sites and (b) would make
every unmocked-variant respx fixture raise. Not worth it.

**Proof.** A homepage that fails once and succeeds on retry yields text; a
homepage that always fails still raises after exactly two attempts.

**Shipped as proposed.**

### D4 — score links instead of keyword-matching them

**Today.** `_is_content_link` is a boolean substring test, and `_select_links`
keeps "content-ful first, then first-seen order", capped at 5. So `/login`,
`/privacy-policy`, `/cookies` and `/kariyer` are all equally eligible, a
fragment link (`/about#team`) is crawled as if it were a distinct page, and the
anchor text — often the only signal on a site with opaque paths (`/p/12`) — is
ignored entirely.

**Change.** A small, explicit scoring function over (path, anchor text):

* **positive** for the existing content keywords (about, products, services,
  solutions, team, technology + the Turkish equivalents), in the path *and* in
  the anchor text;
* **negative** for paths that never describe a company: legal/privacy/terms/
  cookies/kvkk, careers/jobs/kariyer, login/register/account, cart/checkout/
  sepet, search, sitemap, feed;
* **hard exclusion** for non-document extensions and for `mailto:`/`tel:`;
* **depth penalty** so `/products` outranks `/products/2019/archive/x`;
* fragments stripped and URLs de-duplicated *after* stripping, so `/about` and
  `/about#team` are one page.

Ordering is stable (score, then first-seen) so the crawl stays deterministic.

**Risk** low; it only re-orders and prunes candidates within the existing
5-link cap.

**Proof.** Given a homepage linking `/privacy`, `/kariyer`, `/about` and
`/urunler`, the two content pages are crawled first; `/about#team` does not
consume a second slot; a `mailto:` link is never fetched.

**Shipped as proposed**, with one addition the "hard exclusion" line implied:
`login`/`cart`/`checkout`-class paths are dropped outright rather than merely
ranked last, because there is no site on which they are the sixth-best page. The
negative-keyword list only *demotes*; the two are separate lists on purpose.

### D5 — stop paying for the same footer six times

**Today.** `_clean_text` flattens a page into one string, and `discover`
concatenates all six. Every page repeats the header, nav (`<nav>` is stripped,
its markup-free equivalents are not), footer, cookie notice and legal blurb, so
a six-page crawl spends a large share of its 20 000-character budget re-reading
the same boilerplate — budget that the product pages never get.

**Change.** Extract each page's visible text as **blocks** rather than one
string, and drop a block whose normalized form was already seen on an earlier
page. Plus a per-page cap (`MAX_PAGE_CHARS`) on *subsequent* pages, so one
enormous page cannot starve the rest; the homepage keeps the full budget,
because on a one-page site it is the whole crawl.

**Why block-level and not sentence-level.** Blocks are what the HTML already
gives us (`get_text(separator="\n")`), they are stable across pages, and
sentence-splitting a five-language corpus is a research project.

**Proof.** Two pages sharing a footer emit that footer once; a single-page crawl
is byte-identical to today (the truncation tests stay green).

**Shipped as proposed.** Deduplication is keyed on a fold+casefold+collapse of
the block, so a footer that differs only in whitespace or capitalization between
templates still collapses to one copy.

---

## 3. Workstream K — KYC: ask for what we need, keep only what is true

### K1 — the profile gains the two fields prompts actually need

**Today.** The `KYC` model has nine fields, and *none of them is the buying
category*. `prompts.py` therefore reverse-engineers a category from `keywords`,
which is a field the model fills with whatever seemed salient — including spec
attributes. The single most important input to a GEO question is the one field
we never asked for.

**Change.** Two additive fields, both defaulted:

* `category: str` — the one category a buyer would search for
  ("industrial robots", "tactical UAVs", "CRM software"). Explicitly *not* the
  company, not a model name, 1–4 words.
* `use_cases: list[str]` — 2–6 short buyer-facing phrases naming what people use
  this for ("warehouse automation", "border surveillance").

**Model-touch caveats** (the same ones step 6 of the previous doc carries):
both fields **must** default, or `KYC(company="")` in
`scripts/gen_methodology.py` crashes the contract job. No OpenAPI change is
expected (`ResultOut.kyc` is `dict[str, Any] | None`) and no migration (`kyc` is
schemaless JSONB) — but `make gen-types` must be run and proven a zero diff.

**Proof.** `make gen-types` is a zero diff; `KYC(company="")` still constructs;
the mock profile carries both fields so DRY_RUN exercises them.

**Shipped as proposed.** `frontend/lib/contracts.ts` and `KycCard` were updated
in the same change — the hand-maintained KYC interface is the frontend's copy of
this model, and letting it drift is how the card silently stops showing what the
pipeline knows.

### K2 — an extraction prompt that defines its fields

**Today.** The prompt lists field names and four rules. It never says what a
"keyword" is, so the model answers with spec sheets; never says what an alias
is, so it answers with marketing taglines; never bounds list lengths, so a
verbose site yields 40 keywords of which 35 are noise.

**Change.** Rewrite as a field-by-field contract: one line per field saying what
belongs in it, what does not, and how many items. Keep every existing
anti-hallucination rule verbatim (they work), keep "Respond with ONLY the JSON
object" (the `MockProvider` coupling depends on the literal phrase
`json object`), and add the two new fields with examples of a good and a bad
`category`.

**Risk** medium — this is the one change whose effect is not deterministic.
Mitigation: the parse/repair/retry path (step 3 of the previous doc) is
unchanged, the sanitizer below is a hard backstop on shape, and the
`"json object"` coupling has an existing test.

**Proof.** The existing prompt tests still pass (anti-guessing rules +
`json object` present), plus new assertions that each field is defined and that
`category` carries an example.

**Shipped as proposed.**

### K3 — sanitize every value before anything downstream sees it

**Today.** Whatever JSON validates is what we persist and what prompts consume.
`""`, `"N/A"`, `"-"`, `"Not specified"`, a 400-word "description" pasted into a
keyword slot, the same term three times in different capitalizations, the
company's own name in `competitors` — all of it passes.

**Change.** One sanitation pass (`app/pipeline/sanitize.py`, shared with
prompts) applied to every field:

* trim, collapse whitespace, strip wrapping quotes/markdown emphasis;
* drop placeholder junk (`n/a`, `none`, `unknown`, `not specified`, `various`,
  `-`, `null`, `tbd`);
* de-duplicate case- and diacritic-insensitively, preserving first-seen order
  and the original spelling;
* cap per-field item counts and per-item length, so one field cannot dominate;
* drop from `competitors` anything that *is* the company (or one of its
  aliases) — a self-listed competitor becomes an "alternatives to <us>" prompt.

**Proof.** A profile of junk sanitizes to empty lists rather than junk lists; a
competitor equal to the company is removed; caps hold.

**Shipped as proposed.**

### K4 — ground the proper nouns in the crawl

**Today.** `products`, `competitors` and model-supplied `aliases` are taken on
faith. An invented product name becomes a brand-probe prompt about a product
that does not exist; an invented competitor becomes an "alternatives to X"
prompt; an invented alias silently *inflates the GEO score*, because
`footprint.detect` counts any answer containing it.

That last one is the real reason this section exists: **a hallucinated alias is
indistinguishable, downstream, from a genuine mention.**

**Change.** After sanitation, drop any `product`, `competitor` or
model-supplied `alias` whose normalized form does not appear in the crawl text
(folded + casefolded + separator-collapsed containment — the same tolerances
`footprint` matches with, so a name written `Coca-Cola` on the site and
`Coca Cola` by the model still grounds).

Three guards keep this from doing harm:

1. **It never touches the inferred fields.** `description`, `industry`,
   `keywords`, `category`, `use_cases` are *supposed* to be the model's words —
   often an English rendering of Turkish copy. Grounding them would delete the
   translation the prompt explicitly asked for.
2. **It never removes the minted aliases.** Company name, ASCII-folded form,
   legal-suffix stem and registrable domain are added *after* grounding and are
   never subject to it.
3. **It only runs when there is a corpus to check against.** Below
   `MIN_GROUNDING_CHARS` (1 000) the crawl is too thin to prove a negative, so
   grounding is skipped entirely. This is also what keeps DRY_RUN honest: the
   mock's fictional profile describes a company that `example.com` has never
   heard of, and a 200-character page is not evidence of absence.

**And it is off for checker rows.** A checker analysis has no crawl at all — its
"source text" is the literal string `Brand: X. Category: Y.`, and the model's
competitor knowledge is the *only* signal there is. `run_pipeline` therefore
passes `verify_against_source=False` for `kind='checker'`. Grounding a profile
against a sentence we wrote ourselves would delete everything and quietly
degrade every checker run to the `"the market leaders"` fallback.

**Proof.** An invented product/competitor/alias is dropped from a real-size
corpus; a genuine one written with different diacritics or hyphens survives; a
thin corpus drops nothing; a checker row drops nothing.

**Shipped as proposed.**

### K5 — the usability gate learns about the new fields

**Today.** `require_usable` accepts a profile with any of
`keywords`/`services`/`industry`. A profile whose only topic signal is the new
`category` would be rejected — the gate would refuse the *best* possible input.

**Change.** `category` and `use_cases` count as topic signals, and the check runs
against the **sanitized** values, so a profile whose only "keyword" was `"N/A"`
is now correctly rejected instead of buying 60 calls about `"solutions"`.

**Proof.** `category`-only and `use_cases`-only profiles pass; a junk-only
profile now fails.

**Shipped as proposed.**

---

## 4. Workstream P — prompts: ask what a buyer would ask

### P1 — a typed, filtered, ranked topic pool

**Today.** `_question_topics` concatenates `keywords + short services +
industry`, drops anything over 5 words, and falls back to the literal
`"solutions"`. Every survivor is treated as interchangeable and every one of
them is fed to every template. That is how `"payload capacity"` becomes a
manufacturer question.

**Change.** Build a pool of typed topics, in confidence order:

| Priority | Source | Kind |
|---|---|---|
| 1 | `kyc.category` | category |
| 2 | `kyc.use_cases` | use-case |
| 3 | `kyc.keywords` that survive the category filter | category |
| 4 | short `kyc.services` | service |
| 5 | leading `kyc.industry` segment | category |

with a **category filter** that rejects phrases which cannot be a category:
containing digits or model-code shapes (`V10`, `RPG-7`), containing `%`/`+`/`&`
or a slash, ending in a spec-attribute noun (`capacity`, `capability`,
`endurance`, `range`, `weight`, `accuracy`, `immunity`, `compliance`, ...), or
being a bare adjective phrase (`EW immune`, `anti-armor`).

The **kind** matters because it decides the verb: you ask who *manufactures*
industrial robots and who *provides* systems integration, and getting that
backwards is the tell that a question was generated rather than asked.

**Honest limit, stated plainly.** No heuristic reliably separates "category"
from "attribute" in free text — `"fiber optic"` passes every filter above and is
still not a category. The filter reduces noise; the actual fix is K1, which
*asks* for the category instead of guessing it. The two ship together for that
reason.

**Proof.** On the pinned `beyondtech` KYC, no prompt contains `payload
capacity`, `flight endurance`, `EW immune`, `RPG-7 capability` or `anti-armor`;
`category`, when present, is topic #1.

**Shipped as proposed.**

### P2 — templates that vary, and that never name the brand

**Today, two defects.**

*Rotation.* `_question_specs` walks `CATEGORIES[step % 6]` and
`topics[step % len(topics)]` in lockstep. When a profile has exactly 6 topics —
entirely normal — topic *i* is only ever paired with category *i*: six distinct
questions out of a possible thirty-six, after which generation falls through to
the numbered padders. A rich KYC produces *less* variety than a sparse one.

*Brand leak.* Nothing stops a topic from containing the company name. If
`keywords` carries the brand (common — SEO copy is full of it), we generate
"What are the best <Brand> options available today?", ask four engines, and
count the brand's appearance in the answers as a footprint. **That is a
self-fulfilling score**, and it is the most severe correctness bug in this
document.

**Change.**

* Rotate with `CATEGORIES[(round + topic_index) % len(CATEGORIES)]`, so every
  topic meets every shape before any pair repeats.
* Kind-aware phrasing per shape (manufacturers/providers/companies).
* Two to three phrasings per shape, so a 30-prompt panel does not read like a
  mail merge.
* A **hard invariant, enforced at the exit of `generate_prompts`**: no prompt
  outside the `brand-probe` category may contain the company name or any alias,
  compared with the same folding `footprint` uses. A leaking candidate is
  discarded and the next one takes its place.

**Proof.** A KYC whose keywords include the brand yields zero non-probe prompts
containing it; six topics × six shapes yields 36 distinct questions before any
padder is reached; the existing category-cycling and brand-probe-minority tests
stay green.

**Shipped as proposed.** The brand-leak filter is applied to the topic pool
*and* re-checked on the finished text, because a competitor named after the
company (`"Globex Systems"` for `Globex`) can reintroduce the name through the
`alternatives` slot.

### P3 — the checker set reads the same better fields

**Today.** `checker_prompts._primary_topic` prefers `keywords[0]`, with the same
attribute-noise exposure.

**Change.** Prefer `category`, then `use_cases`, then filtered keywords, then
industry, then services — the same ranking as P1, sharing the same filter.

**What must not change, and did not.** The 12 templates' **wording and order**
are untouched, so `checker_prompts.VERSION` stays `checker-en-v1` and
`checker_methodology.json` is byte-identical (the artifact is generated from
`KYC(company="")`, where every source is empty and the neutral `"solutions"`
fallback still stands in). Only the *substituted value* on a live run improves —
that is per-run data, not the versioned template.

**Proof.** `make gen-types` is a zero diff, and a test asserts the generated
methodology prompts are unchanged.

**Shipped as proposed.**

---

## 5. What this buys, in one table

| Failure that used to reach production | Now caught by |
|---|---|
| Mojibake from an undeclared charset | D1 |
| A header-less PDF parsed as page copy | D2 |
| One dropped TCP connection kills a paid run | D3 |
| The crawl budget spent on `/privacy` and `/kariyer` | D4 |
| The same footer read six times | D5 |
| The category is guessed from spec attributes | K1 + P1 |
| `"N/A"` persisted as a keyword and asked about | K3 |
| A hallucinated alias inflating the GEO score | K4 |
| A hallucinated product/competitor generating prompts | K4 |
| Six topics collapsing to six questions | P2 |
| **The brand's own name inside the question we score** | **P2** |

---

## 6. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| Grounding drops a legitimate product | medium | Fold/case/separator tolerance; skipped under `MIN_GROUNDING_CHARS`; never applied to inferred fields or minted aliases; off for checker rows |
| The rewritten KYC prompt regresses on some site shape | medium | Parse repair + one bounded retry unchanged; sanitizer is a hard shape backstop; `json object` coupling pinned by test |
| Block dedup removes genuinely repeated copy | low | Only exact (normalized) block repeats across *different* pages; a single-page crawl is byte-identical |
| Link scoring skips a page that mattered | low | Scoring only reorders within the existing 5-link cap; only never-descriptive paths are hard-excluded |
| New KYC fields break the contract gate | low | Both defaulted; `make gen-types` zero-diff proven |

---

## 7. Deliberately not in this plan

* **Turkish suffix-aware matching (step 2b) and recording site language
  (step 6).** Unchanged from
  [`discovery-kyc-improvements.md`](discovery-kyc-improvements.md): they revive
  roadmap §2c scope the operator parked on 2026-07-10, and that call is not
  engineering's to make. Everything above is language-neutral;
  `test_footprint.py` still pins that `Yankinin` does not match `Yanki`.
* **LLM-generated prompts.** The higher ceiling, and the roadmap's stated
  Next-phase lever — but it adds an unmetered paid call while tech-debt #27 is
  open, needs its own validation harness (the brand-leak invariant becomes
  *load-bearing* rather than a backstop), and would make the prompt set
  non-deterministic and therefore unauditable against the "show our work" wedge.
  K1 captures most of the quality by asking the *existing* call for the field we
  actually needed. Revisit after #27.
* **Counting KYC-stage spend (tech-debt #27).** Still deserves its own change:
  it re-tunes what the $5 daily cap measures. This plan does not widen the gap —
  it adds no call.
* **Concurrent crawling, robots.txt, sitemap.xml.** Unchanged reasoning from the
  previous doc: latency (not quality) for the first; an unconditional extra
  request that reddens every `@respx.mock` fixture for the other two. Sitemap
  remains the most valuable of the three and is the natural next discovery step.
* **Sampling each prompt more than once, position/sentiment weighting.** That is
  roadmap §2b's *scoring* depth, downstream of everything here.

---

## 8. Proof of work

```
make lint && make typecheck && make test && make gen-types   # gen-types: zero diff
```

**Measured:** backend **321 passed / 3 skipped** (Postgres-gated), up from 263;
frontend **70 passed**. `ruff check`, `mypy app`, `tsc --noEmit` and `eslint`
all clean. `make gen-types` a zero diff across `openapi.json`,
`checker_methodology.json` and `types.ts`.

Tests added cover: charset decoding (both precedence directions), binary
sniffing with and without a Content-Type, homepage retry (success and bound),
link exclusion/anchor-text scoring/fragment de-duplication, cross-page block
dedup and the per-page cap, the two new KYC fields, sanitation (junk, dedupe,
caps, self-competitor), grounding (invented values dropped, diacritic/separator
spellings kept, inferred fields untouched, minted aliases untouched, thin-corpus
skip, checker opt-out), the topic filter against the pinned real-world KYC,
full topic × shape rotation, number- and kind-aware phrasing, and the brand-leak
invariant.

**Checked live, not only in fixtures.** Against `beyondtech.com.tr` — the SPA
the pinned fixtures were taken from — the crawl corpus went from opening with
React Router error strings and minified code to 20 000 characters of the site's
real Turkish copy, and the generated prompt set no longer contains a single
spec-attribute question. The intermediate attempt that also stripped object
punctuation was reverted after measuring what it cost (tech-debt #31).
