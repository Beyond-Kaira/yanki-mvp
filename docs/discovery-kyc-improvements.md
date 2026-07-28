# Discovery + KYC extraction — improvements

**Status: steps 1, 2a, 3, 4 and 5 are implemented** (branch
`feat/discovery-kyc-improvements`, one commit each, `make test` green and
`make gen-types` a zero diff). **Steps 2b and 6 are not built** — they revive
scope the operator parked, and that call is not engineering's to make. See the
bucket table below.

Discovery (`backend/app/pipeline/discovery.py`) and KYC extraction
(`backend/app/pipeline/kyc.py`) feed everything after them. The KYC profile is
what `prompts.py` writes questions from, and `kyc.company` + `kyc.aliases` *are*
the footprint `scoring.py` counts. Garbage in these two steps does not show up as
an error — it shows up as a plausible-looking GEO score that is quietly wrong.
That is why they are worth a pass of their own.

Steps 1–5 do **not** touch the `KYC` Pydantic model (`kyc.py:25-34`) and need no
contract regeneration — confirmed by a zero-diff `make gen-types`. **Only Step 6
touches the model.**

## What shipped, and the two steps that still need an operator decision

`docs/roadmap.md` §2c is **deferred by operator decision (2026-07-10)**: "the
whole product ships English-only for now", revived "only on the operator's word".
Two items in that deferred list overlap this proposal:

- "Turkish suffix-aware brand/footprint matching" — **part of Step 2**
- native Turkish prompt generation — the thing **Step 6** exists to unblock

So the steps split into two buckets, and they were treated differently:

| | Steps | Needs | State |
|---|---|---|---|
| **Clear to build** | 1, 2a, 3, 4, 5 | normal review | **implemented**, one commit each |
| **Reviving deferred §2c scope** | 2b, 6 | operator sign-off first | **not built** — awaiting that decision |

Step 2 is split below into **2a** (language-neutral matching robustness, which
helps English brands too) and **2b** (Turkish suffixation specifically). That
split is the whole reason to read Step 2 carefully rather than approving it
wholesale — and it is why 2a could ship while 2b waits.

This was flagged rather than quietly shipped: the roadmap note is explicit that
the deferral is an operator call, not an engineering one. `test_footprint.py`
carries a row asserting `Yankinin` still does **not** match `Yanki`, so the
boundary between 2a and 2b is enforced by a test rather than by memory.

---

## Step 1 — Parse JSON-LD before we throw it away

**Today.** `_clean_text` decomposes every `<script>` tag before extracting text
(`discovery.py:93`), and that includes `<script type="application/ld+json">`.
Nothing in the repo parses JSON-LD at all. So on any site that publishes
schema.org markup — which is most commercial sites, because SEO tooling puts it
there — we delete the cleanest description of the company that exists and then
ask an LLM to reconstruct it from marketing prose.

`Organization` / `Product` blocks typically carry `name`, `legalName`,
`description`, `brand`, product names, `sameAs` (social + registry profiles) and
`address`. That maps almost field-for-field onto our `KYC` model.

**Change.** Add `_jsonld_text(html)` that re-parses the *already fetched* HTML,
walks `soup.find_all("script", type="application/ld+json")`, `json.loads` each
block inside its own `try/except` (tolerating a top-level array and `@graph`),
and emits a bounded, flattened text segment. Call it on `home_html` and each
`page_html`, and place its output **first** in the `combined` assembly
(`discovery.py:293-297`) so it survives the `[:MAX_CHARS]` cut. Leave
`_clean_text` stripping scripts for the visible-text pass — this is a second,
separate read of the same bytes.

**Why it improves KYC.** `company`, `description`, `products` and alias-worthy
`sameAs` values arrive as facts instead of inferences. These are exactly the
fields `prompts.py` and `footprint.py` depend on.

**Effort** small. **Risk** low — it is *fetch-free*, so it cannot trip the
constraint that every discovery test runs under `@respx.mock`, where an unmocked
request raises. Must not follow `sameAs` URLs (a fetch would have to go through
the SSRF-guarded client) and must bound its own output.

**Proof it worked.** Unit test: HTML with an `Organization` block → its `name`
and `description` appear in `discover()` output. Existing fixtures carry no
JSON-LD, so `_jsonld_text` returns `""` and the truncation/SPA tests stay
byte-stable.

**Shipped as proposed**, with two additions the "bound its own output" line
implied but did not spell out: a `MAX_JSONLD_CHARS = 4_000` budget so JSON-LD can
never crowd out real page copy, and cross-page dedup, because sites repeat one
`Organization` block on every page and paying for it six times is waste. Keys
harvested: `name`, `legalName`, `alternateName`, `description`, `slogan`,
`brand`, `sameAs`, and the nested `addressLocality`/`addressCountry` (which feed
`locations`). Recursing into every container value handles `@graph`, top-level
arrays and nested nodes without special-casing any of them.

---

## Step 2 — Make footprint matching survive Turkish

**Today.** `footprint.detect` compiles `r"\b" + re.escape(term) + r"\b"` with
`re.IGNORECASE` (`footprint.py:40`), and `_ensure_alias` only ever adds the
verbatim company name and the bare registrable domain label
(`kyc.py:127-130,147-148`).

We measured the actual gaps rather than assuming them:

| answer text | alias | result |
|---|---|---|
| `TÜRK Holding` | `Türk` | **hit** — case folding already works |
| `TÜRK Holding` | `Turk` | **miss** — diacritics not folded |
| `İşbank` | `Isbank` | **miss** — Turkish dotted İ |
| `Yankinin ürünleri` | `Yanki` | **miss** — agglutinative suffix, no `\b` after the stem |
| `Coca Cola` | `Coca-Cola` | **miss** — hyphen vs space |

Worth being precise, because it is easy to overstate: `re.IGNORECASE` on `str`
patterns **is** Unicode-aware, so plain case differences already match. The four
real misses are diacritic folding, Turkish dotted-I, suffixation and
hyphen/space.

### 2a — language-neutral matching robustness (clear to build)

Rows 2, 3 and 5 of that table are not really "Turkish" problems; they are
matching problems that happen to bite hardest in Turkish:

- **Diacritic folding** helps any non-ASCII brand — `Nestlé`, `Müller`, `Škoda`.
- **Hyphen/space equivalence** is a pure-English win as often as not
  (`Coca-Cola`, `Hewlett-Packard`, `T-Mobile`).
- **Dotted-İ** is a correctness bug in Unicode case handling, not a feature
  request.

**Change.** In `footprint.py`, fold both the answer text and each term (reuse the
`_TR_FOLD` map that already exists at `discovery.py:62-74` rather than writing a
second one) and treat hyphen and space as interchangeable. In
`kyc._ensure_alias`, additionally mint an ASCII-folded form and a
legal-suffix-stripped form (A.Ş. / A.S. / Ltd. / Inc. / GmbH) of the company
name.

**Effort** medium. **Risk** medium: looser matching risks false positives on very
short brands. Keep the `_MIN_TERM_LEN = 2` floor (`footprint.py:15`) and the
word-boundary anchor; add only the tolerances above. This adds alias *values* to
an existing list — no model change, no contract work. Must preserve the invariant
that company + registrable domain are always aliases.

**Shipped, with one deviation from the instruction above.** The fold did *not*
end up reusing `discovery._TR_FOLD` in place; it moved to a new
`backend/app/pipeline/textfold.py` that both modules import. The reason is a
constraint the proposal missed: `footprint.detect` matches against folded text
but slices the user-facing snippet out of the **original** by index, so the fold
must be **length-preserving** — and `_TR_FOLD` was only ever used *after*
`casefold()`, which is not. `"İ".casefold()` is two codepoints (`i` +
U+0307 combining dot above), so the old approach would both corrupt every
snippet after an `İ` and fail to match `İşbank` against `Isbank` at all. The
shared table is therefore case-*preserving* and 1:1, with `re.IGNORECASE` doing
the case work; German `ß` is deliberately excluded because it expands to `ss`.
The proposal's actual intent — one map, not two — is honoured. Tests pin the
length invariant and the snippet's original spelling.

`kyc._ensure_name_aliases` mints the folded and suffix-stripped forms only when
they differ from an alias already present, so an ASCII, suffix-free brand gains
nothing and the alias chips in `KycCard` stay clean. The folded alias is not
redundant with the footprint fold: `checker_summary._exclusions` suppresses
competitors by `casefold()` alone, so `Türk Holding` would otherwise fail to
suppress a reported `Turk Holding`.

### 2b — Turkish suffix awareness (**deferred scope — needs operator sign-off**)

Row 4 (`Yankinin` ↔ `Yanki`) needs agglutinative-suffix handling, which is
verbatim the deferred roadmap item "Turkish suffix-aware brand/footprint
matching" (`docs/roadmap.md:102`). It is a small change on top of 2a — a suffix
boundary allowance after the stem — but it is deferred *scope*, not deferred
*effort*. Do not slip it in with 2a.

**Why the split matters.** Shipping 2a alone is a straight correctness win under
the current English-only decision. Shipping 2b re-opens a product bet the
operator explicitly parked.

**Not shipped — awaiting operator sign-off.** `test_footprint.py` asserts the
current (2a-only) behaviour: `Yankinin` does **not** match `Yanki`. That test is
the enforcement of the boundary, and it is the test to change when 2b is
approved.

**Proof either worked.** Unit tests for each row of the table above, plus a
false-positive guard on a 2-character brand. Both landed for 2a: one
parametrised case per row, plus guards that `GE` does not leak into
`General`/`German` and that `Coca-Cola` does not bridge "Coca leaves and cola
nuts".

---

## Step 3 — Let the KYC call survive a formatting slip

**Today.** `generate_kyc` makes exactly one attempt (`kyc.py:134-145`). A
`JSONDecodeError`, a non-dict, or a `ValidationError` each raise `PipelineError`
immediately. Correctness rests entirely on the model obeying "Respond with ONLY
the JSON object" plus `_strip_fences` (`kyc.py:54,66-75`). One `Here is the
profile:` prefix burns the whole job *after* discovery has already been paid for,
and the user sees a bare "could not read the company profile".

**Change.** On a parse failure, first try extracting the outermost `{ … }` span
and re-parsing — no network, no cost. Only if that fails, make **one** bounded
retry of `provider.generate`. Only then raise.

**Effort** small. **Risk** low, with one lockstep constraint: `MockProvider`
returns the canned KYC profile only because the prompt contains the literal
`"json object"` (`mock.py:46-50`, satisfied by `kyc.py:39`). A plain retry
re-sends the same prompt and stays green; if we ever send a *different* repair
prompt it must keep that phrase or `mock.py` must gain a matching branch in the
same PR, or DRY_RUN and the e2e break.

**Proof it worked.** Unit test with a canned provider whose first response wraps
valid JSON in prose → `generate_kyc` returns a valid `KYC` instead of raising.

**Shipped as proposed.** The retry re-sends the same prompt, and a test asserts
both prompts are byte-identical *and* both contain `"json object"`, so the
`MockProvider` coupling fails loudly rather than silently. Tests also pin that
the free repair does not trigger a second round trip, that the happy path still
costs exactly one call, and that the retry is bounded at one rather than looping.
The two user-facing messages stayed distinct ("could not read the company
profile" vs "the company profile was incomplete") and now have a test.

---

## Step 4 — Guard `_fetch` on Content-Type

**Today.** `_fetch` returns `response.text` for any 200 with no Content-Type and
no size check (`discovery.py:135-142`) — notably unlike `_fetch_script`, which
does guard content-length (`discovery.py:152-154`). If `_select_links` picks a
`.pdf` or an image, its bytes go through BeautifulSoup and `_clean_text` and the
resulting mojibake eats the 20k budget that real page copy needed.

**Change.** After the 200 check, skip anything whose Content-Type is not
`text/html` / `application/xhtml+xml`, and apply the same length guard
`_fetch_script` already uses.

**Risk** low **but** with a trap worth naming: many `respx` mocks in the existing
suite set no Content-Type header at all. Treat missing/empty as HTML
(permissive), or the whole discovery suite goes red. That also matches the
codebase's existing fail-open stance — `net_guard` treats an unresolvable host as
public so CI and offline dev keep working.

**Proof it worked.** Unit test: a link mocked as `application/pdf` is skipped and
its bytes never reach `_clean_text`; a header-less mock still parses.

**Shipped as proposed.** The length guard is now shared with `_fetch_script` via
`_within_size`, and there are two extra tests: an oversized `content-length` is
skipped, and a non-HTML *homepage* raises `PipelineError` rather than producing
garbage KYC input. The fail-open-on-missing-Content-Type choice has a test of its
own so it reads as a decision rather than an accident.

---

## Step 5 — Refuse to pay for a fan-out on a useless profile

**Today.** `company: str` has no `min_length`, so `company=""` validates
(`kyc.py:26`); `_ensure_alias(kyc, kyc.company)` then silently no-ops, leaving
footprint with nothing to match. Separately, when no topic signal survives,
`_question_topics` falls back to the literal string `"solutions"`
(`prompts.py:108-109`), and `_make` falls back to `"the market leaders"` and
`"worldwide"`. Either way the run continues into `run_execute`
(`runner.py:118`), which fans out up to `max_responses_per_job` — **default 60**
(`config.py:36`) — paid provider calls asking generic questions about
"solutions", and scores the answers against an empty brand.

That is the single most expensive step in the pipeline, spent on input we already
know is unusable.

**Change.** After `generate_kyc` (`runner.py:91`), require a non-empty `company`
**and** at least one real topic signal (any of `keywords` / `services` /
`industry`). Otherwise raise a distinct `PipelineError` with an honest message.

**Effort** small. **Risk** low if the threshold stays conservative — reject only
*empty company* or *zero topics*, never thin-but-legitimate sites. It is a
validation gate, not a schema change. In DRY_RUN the mock returns a full canned
profile, so the `example.com` e2e happy path never trips it. Must raise only
`PipelineError` so the worker surfaces a clean message rather than a stack trace.

**Proof it worked.** Unit test: a provider returning `{"company": ""}` raises,
and `run_execute` is asserted **not** to have been called.

**Shipped, with two decisions the proposal left open.**

1. **Where the gate sits.** It runs *after* the KYC step commits, not before, so
   the offending profile stays on the failed row and an operator can see exactly
   what came back. Failing without persisting the evidence would have made these
   failures much harder to diagnose than the runs they replace.
2. **Checker rows.** `checker_prompts` has the same `"solutions"` fallback as
   `prompts.py`, so the waste is identical on that path — but a checker's brand
   and category are validated at submit time, and a terse model reply that does
   not echo the category into `keywords`/`services`/`industry` must not fail a
   legitimate public submission. So `require_usable` takes a `known_topic`, and
   the runner passes `analysis.category` for checker rows. The empty-company
   check still applies to both paths, because with no company `footprint` has
   nothing to match no matter where the row came from.

Tests cover both useless shapes (empty company, zero topics) asserting
`run_execute` is never called, and that a thin-but-legitimate profile with a
single keyword, service *or* industry passes.

---

## Step 6 — Record what language the site is in (**deferred scope — needs operator sign-off**; touches the model)

> This step exists only to unblock `docs/roadmap.md` §2c, which is currently
> deferred English-only by operator decision. It is harmless on its own — it
> changes no behaviour — but it is the first stone of a parked road. Approve it
> as "we want the input recorded from now on", or decline it as premature.

**Today.** There is no language field anywhere, and the KYC prompt forces every
field into English (`kyc.py:50-51`). `prompts.generate_prompts` has no language
parameter and every template is English (`prompts.py:120-132`). So a Turkish
company whose buyers actually query engines in Turkish is measured in the wrong
language — and we do not even record that fact.

**Change (deliberately narrow).** Add `language: str = ""` to the `KYC` model and
populate it deterministically: read `<html lang>` in discovery and fall back to
the ccTLD using the map that already exists (`kyc.py:102-124`).

**Honest limit.** This localizes nothing by itself. Its value is that it is the
missing *input* every localization effort needs, and it makes the analysed site's
language visible in the persisted profile. Do not expect a score change from this
step alone.

**Model-touch caveats.**

- The field **must** carry a default. A required field crashes `KYC(company="")`
  in `scripts/gen_methodology.py:48` and fails the contract job.
- **No** OpenAPI/types change is expected, because `ResultOut.kyc` is
  `dict[str, Any] | None` (`schemas.py:129`), and **no** alembic migration,
  because `kyc` is schemaless JSONB. Still run `make gen-types` and prove a
  **zero diff** — that is what the CI contract gate checks (`ci.yml:92-98`).
- If the field is ever fed into `checker_prompts.generate`, then
  `checker_methodology.json` changes and `checker_prompts.VERSION` **must** be
  bumped. In this step it feeds nothing, so methodology output stays identical.

**Proof it worked.** `<html lang="tr">` → `kyc.language == "tr"`; a `.com.tr` site
with no `lang` attribute falls back to `tr`; `make gen-types` produces no diff.

**Not shipped — awaiting operator sign-off.** Nothing in the implemented steps
depends on it, and no implemented step touches the `KYC` model, so this remains a
clean, self-contained decision to take later.

---

## Cost

No step adds a paid call on the happy path — Step 3 has a test asserting exactly
one call when the first response parses. Step 5 *saves* up to ~60 calls per junk
run. Step 3 adds at most one extra KYC call, on failure paths only.

One thing the team should know before approving Step 3: `generate_kyc` discards
`result.cost_usd` (`kyc.py:134`), and the only dollar cap sums the *execute*
step's `responses.cost_usd` against `checker_daily_usd_cap = $5` per 24h
(`config.py:76`, `rate_limit.py:280-334`). **KYC-stage spend is invisible to
every cost control today.** The retry is roughly $0.01 and will not move the cap
— because nothing counts it. Recording KYC cost is worth doing, but it re-tunes
what feeds that cap and deserves its own change, so it is not bundled here.

## Deliberately not proposing yet

- **Async/concurrent crawl.** Worst case today is sequential: 6 fetches at a 15s
  timeout. It is a real latency win but not a *KYC quality* win, and it means
  re-wiring the SSRF event hook that must fire on every fetch and every redirect
  hop (`discovery.py:262-267`). Worth its own PR, under a latency lens.
- **robots.txt / sitemap.xml.** Both add an unconditional new network request,
  which raises under `@respx.mock` and reddens the entire discovery suite until
  every fixture gains routes. robots.txt is etiquette rather than quality;
  sitemap could genuinely improve page selection. Defer, but do not forget —
  crawling as `YankiBot/0.1` while ignoring robots.txt is a defensible position
  we should take *knowingly*.
- **Native provider JSON mode.** Higher quality ceiling than Step 3, but the
  `Provider` Protocol is `@runtime_checkable` with five implementers and a shared
  `execute` call site; any new capability has to be an optional kwarg with a
  default or every provider breaks. Step 3 buys most of the reliability now.
- **Full prompt localization.** The highest-*impact* gap of everything here, and
  genuinely large: localized templates in `prompts.py` and `checker_prompts.py`,
  footprint tolerance for localized forms (Step 2 delivers part of it), and a
  `checker_prompts.VERSION` bump with methodology drift. Not merely "big" — it is
  **parked by operator decision** in `docs/roadmap.md` §2c. Nothing in this
  document should be read as trying to unpark it; Steps 2b and 6 are flagged
  precisely so that decision stays the operator's.
