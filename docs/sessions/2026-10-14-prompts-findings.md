# Prompts & Answers → Drivers & Gaps → Action Plan

User request: implement the approved demo's floating next-step sticker, which
scrolls to the final Drivers & Gaps transition card. Work continues on the user's
existing `feat/overview-prompts-evidence-card` branch. Existing Overview, navigation
and test edits belong to the user and were preserved.

Assumptions: this is a customer reading sequence over the whole current run;
answer-specific filters and backend changes are outside the approved design.
Product copy remains English. The demo's colors map to the application's existing
primary/surface tokens. No commit, push, PR, merge or deployment was requested.

## Implementation

- Added a short introduction to Prompts & Answers and a final findings card.
- Added `PromptFindingsNextStep`, a compact viewport-positioned shortcut that
  scrolls to that card. IntersectionObserver uses AppShell's scrolling `main`
  element and hides the shortcut when the card is visible or has been passed.
- The card links to `/ai-visibility/drivers?analysis=<current-id>` with the ID
  URL-encoded. It moves keyboard focus to that link before scrolling and uses
  instant scrolling for reduced-motion preferences.
- Both prompt/response and GEO-only records support this flow. Empty and
  unfinished runs do not show premature next-step controls.

## Validation

- Frontend TypeScript and scoped ESLint passed; changed source files formatted.
- Existing relevant Vitest suites: **41 tests across 5 files passed** (Overview
  evidence, question breakdown, visibility insights, shell navigation and shared
  analysis content width).
- Real local Next.js UI verified in Chromium with intercepted fixture API data:
  desktop 1440px, mobile 375px and mobile 320px. Sticker fits each viewport;
  keyboard activation scrolls the shell main and focuses the visible card link;
  clicking preserves the run ID on Drivers & Gaps.
- Also verified short-page shortcut suppression, GEO-only records,
  reduced-motion instant scrolling, empty/running states and no browser errors.
- No live provider calls or database writes were used for verification. The
  feature uses the existing fetched data and navigation contracts.

## Handoff

Follow-up request: add the same sticker to Drivers & Gaps. Its “Next step /
Action Plan” shortcut scrolls to the existing “Turn these gaps into a plan”
card. The final link preserves the current analysis ID when opening Recommended
interventions. `AnalysisNextStep` now owns the shared visibility, focus and scroll
behavior; `PromptFindingsNextStep` supplies the original prompt-page copy.
No metric, navigation label or unrelated screen was changed in this follow-up.

Follow-up checks: TypeScript and scoped ESLint passed; 24 relevant existing
frontend tests across five files passed. Chromium verified Drivers & Gaps and
the shared Prompts & Answers behavior at 1440px, 375px and 320px: shortcut fits,
keyboard activation scrolls the shell main, focus reaches the destination link,
the shortcut hides when the card is visible, and navigation preserves the current
run ID. Short pages, reduced motion and unfinished runs were also verified;
Prompts & Answers empty/GEO-only states still pass. No browser errors. Scoped
Prettier and diff whitespace checks passed. No live provider calls or database
writes were used.

Implemented locally; no known blocker or new technical debt. No architectural
boundary changed, so no ADR is required. Updated brandkit behavior, implementation
status, technical-debt maintenance note and operator expectations. Reviewed the
77-file Markdown inventory: existing reference uploads and historical session
logs remain archives; no unrelated document deletion was warranted. The earlier
global resume/past prompts were retained because this user-directed branch task
does not replace their historical planning brief.

## 2026-10-16 publication handoff

The user requested a branch push and a PR. Fetched `origin/main`: the current
branch starts at its current tip, `d0ea659`, and has no existing open PR.
The publication includes the Overview evidence card, AI Visibility navigation
order and both approved next-step shortcuts with their documentation. The
unrelated local PDF under `output/` is excluded.

Pre-publication validation: the full frontend suite passed **540 tests across
85 files**; `npm run lint`, `npm run typecheck`, `npm run build` and
`git diff --check` passed. Earlier fixture-based desktop/mobile browser checks
are recorded above. Backend and contracts were not changed; full backend and
live-stack CI remain separate remote checks.

Next-session prompt: inspect the published PR's checks and preserve the current
Overview → Prompts & Answers → Drivers & Gaps → Action Plan flow. Address any
failed check within the branch's scope. Merge only when the user requests it.
