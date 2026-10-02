"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import Link from "next/link";
import AnalysisBoundSubpage from "@/components/ai-visibility/AnalysisBoundSubpage";
import {
  interventionsFromAnalysis,
  type InterventionDetail,
} from "@/lib/ai-visibility-data";

type Model = ReturnType<typeof interventionsFromAnalysis>;
const PAGE_SIZE = 10;
type ScoreFilter = "all" | "high" | "medium" | "low" | "unscored";

function matchesScore(value: number | null, filter: ScoreFilter): boolean {
  if (filter === "all") return true;
  if (filter === "unscored") return value == null;
  if (value == null) return false;
  if (filter === "high") return value >= 4;
  if (filter === "medium") return value === 3;
  return value <= 2;
}

type FilterOption = { value: string; label: string; hint?: string };

function FilterDropdown({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listboxId = useId();
  const selected =
    options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    containerRef.current
      ?.querySelector<HTMLButtonElement>('[aria-selected="true"] button')
      ?.focus();
    const closeOutside = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("mousedown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  function moveWithArrows(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    if (!open) {
      setOpen(true);
      return;
    }
    const buttons = Array.from(
      containerRef.current?.querySelectorAll<HTMLButtonElement>(
        '[role="listbox"] button',
      ) ?? [],
    );
    if (buttons.length === 0) return;
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === "ArrowDown" ? index + 1 : index - 1;
    buttons[(next + buttons.length) % buttons.length].focus();
  }

  return (
    <div ref={containerRef} onKeyDown={moveWithArrows} className="relative">
      <span className="mb-1 block text-xs font-medium text-surface-subtle">
        {label}
      </span>
      <button
        ref={triggerRef}
        type="button"
        aria-label={`${label}: ${selected.label}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        onClick={() => setOpen((current) => !current)}
        className="flex min-h-[42px] min-w-[190px] items-center justify-between gap-3 rounded-lg border border-surface-border bg-white px-3 py-2 text-left text-sm font-medium text-surface-foreground shadow-sm transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <span className="truncate">{selected.label}</span>
        <svg
          viewBox="0 0 24 24"
          className={`h-4 w-4 shrink-0 text-surface-subtle transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {open ? (
        <ul
          id={listboxId}
          role="listbox"
          aria-label={label}
          className="absolute left-0 top-full z-40 mt-1.5 max-h-64 w-64 max-w-[calc(100vw-3rem)] overflow-y-auto rounded-xl border border-surface-border bg-white p-1 shadow-[0_16px_32px_rgba(11,29,38,0.16)]"
        >
          {options.map((option) => {
            const active = option.value === value;
            return (
              <li key={option.value} role="option" aria-selected={active}>
                <button
                  type="button"
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                    triggerRef.current?.focus();
                  }}
                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary ${active ? "bg-primary-soft text-primary-strong" : "text-surface-foreground hover:bg-surface-muted"}`}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">{option.label}</span>
                    {option.hint ? (
                      <span className="block text-xs text-surface-subtle">
                        {option.hint}
                      </span>
                    ) : null}
                  </span>
                  {active ? (
                    <svg
                      viewBox="0 0 24 24"
                      className="h-4 w-4 shrink-0 text-primary"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="m5 12 4 4L19 6" />
                    </svg>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

const IMPACT_OPTIONS: FilterOption[] = [
  { value: "all", label: "All impact scores" },
  { value: "high", label: "Highest impact", hint: "Scores 4–5" },
  { value: "medium", label: "Medium impact", hint: "Score 3" },
  { value: "low", label: "Lowest impact", hint: "Scores 1–2" },
  { value: "unscored", label: "Not scored", hint: "No impact estimate" },
];

const EFFORT_OPTIONS: FilterOption[] = [
  { value: "all", label: "All effort scores" },
  { value: "low", label: "Lowest effort", hint: "Scores 1–2" },
  { value: "medium", label: "Medium effort", hint: "Score 3" },
  { value: "high", label: "Highest effort", hint: "Scores 4–5" },
  { value: "unscored", label: "Not scored", hint: "No effort estimate" },
];

function category(label: string | null): string {
  return label ? label.replaceAll("_", " ") : "Action";
}

function evidenceLabel(value: string): string | null {
  if (value === "search_visibility.owned_domain_in_results=false")
    return "Owned domain missing from search results";
  if (value === "search_visibility.brand_in_results=false")
    return "Brand missing from search results";
  if (value === "search_visibility.brand_in_results=true")
    return "Brand appears in search results";
  if (value === "mentioned=False" || value === "mentioned=false")
    return "Brand absent from the answer";
  if (
    value === "citation_metrics.target_brand_cited=False" ||
    value === "citation_metrics.target_brand_cited=false"
  )
    return "Brand not cited in the answer";
  if (value.startsWith("search_visibility.brand_best_rank="))
    return `Best search rank: #${value.split("=")[1]}`;
  return null;
}

function ScoreBar({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | null;
  tone: "impact" | "effort";
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="text-surface-subtle">{label}</span>
        <span className="font-semibold tabular-nums text-surface-foreground">
          {value == null ? "Not scored" : `${value}/5`}
        </span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-muted">
        {value != null ? (
          <div
            className={`h-full rounded-full ${tone === "impact" ? "bg-primary" : "bg-warning"}`}
            style={{ width: `${value * 20}%` }}
          />
        ) : null}
      </div>
    </div>
  );
}

function ImpactMap({
  items,
  selectedKey,
  onSelect,
  onReview,
  onClear,
}: {
  items: InterventionDetail[];
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
  onReview: () => void;
  onClear: () => void;
}) {
  const points = new Map<
    string,
    { impact: number; effort: number; indices: number[] }
  >();
  items.forEach((item, index) => {
    if (item.impact == null || item.effort == null) return;
    const key = `${item.impact}-${item.effort}`;
    const point = points.get(key) ?? {
      impact: item.impact,
      effort: item.effort,
      indices: [],
    };
    point.indices.push(index);
    points.set(key, point);
  });

  const selected = selectedKey ? points.get(selectedKey) : null;

  if (points.size === 0) return null;

  return (
    <section
      className="rounded-2xl border border-surface-border bg-white p-5 shadow-sm sm:p-6"
      aria-labelledby="impact-map-heading"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">
            Decision map
          </p>
          <h2
            id="impact-map-heading"
            className="mt-1 text-xl font-semibold text-surface-foreground"
          >
            Impact versus effort
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-surface-subtle">
            The number in each circle shows how many actions share those scores.
            Select a circle to filter the recommendations list by those scores.
          </p>
        </div>
        <span className="rounded-full bg-primary-soft px-3 py-1 text-xs font-medium text-primary-strong">
          Start in the upper left
        </span>
      </div>

      <div className="mt-6 flex gap-3">
        <div className="flex w-5 shrink-0 items-center justify-center text-[11px] font-semibold uppercase tracking-wider text-surface-subtle [writing-mode:vertical-rl] [transform:rotate(180deg)]">
          Higher impact
        </div>
        <div className="min-w-0 flex-1">
          <div className="relative h-64 overflow-hidden rounded-xl border border-surface-border bg-surface-muted/30 sm:h-72">
            <div
              className="absolute inset-0 grid grid-cols-2 grid-rows-2 text-xs font-medium text-surface-subtle"
              aria-hidden="true"
            >
              <div className="border-b border-r border-surface-border bg-primary-soft/40 p-3">
                Higher impact, lower effort
              </div>
              <div className="border-b border-surface-border p-3 text-right">
                Strategic bets
              </div>
              <div className="border-r border-surface-border p-3 self-end">
                Easy to try
              </div>
              <div className="p-3 text-right self-end">Plan carefully</div>
            </div>
            {[...points.values()].map((point) => (
              <button
                type="button"
                key={`${point.impact}-${point.effort}`}
                aria-pressed={selectedKey === `${point.impact}-${point.effort}`}
                aria-label={`${point.indices.length} recommendation${point.indices.length === 1 ? "" : "s"} with impact ${point.impact} of 5 and effort ${point.effort} of 5`}
                title={`Impact ${point.impact}/5 · Effort ${point.effort}/5`}
                className={`absolute z-10 flex h-9 w-9 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 text-xs font-bold shadow-md transition-transform hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 sm:h-10 sm:w-10 ${selectedKey === `${point.impact}-${point.effort}` ? "border-primary bg-white text-primary ring-4 ring-primary/20" : "border-white bg-primary text-white"}`}
                style={{
                  left: `${10 + (point.effort - 1) * 20}%`,
                  top: `${90 - (point.impact - 1) * 20}%`,
                }}
                onClick={() =>
                  onSelect(
                    selectedKey === `${point.impact}-${point.effort}`
                      ? null
                      : `${point.impact}-${point.effort}`,
                  )
                }
              >
                {point.indices.length}
              </button>
            ))}
          </div>
          <div className="mt-2 flex justify-between text-[11px] font-medium text-surface-subtle">
            <span>Lower effort</span>
            <span>Higher effort</span>
          </div>
        </div>
      </div>
      {selected ? (
        <div
          role="region"
          aria-label="Selected recommendations"
          aria-live="polite"
          className="mt-5 rounded-xl border border-primary/20 bg-primary-soft/30 p-4 sm:p-5"
        >
          <p className="text-sm text-surface-foreground">
            Showing {selected.indices.length} action
            {selected.indices.length === 1 ? "" : "s"} with impact{" "}
            {selected.impact}/5 and effort {selected.effort}/5.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-2">
            <button
              type="button"
              onClick={onReview}
              className="text-sm font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              Review matching actions →
            </button>
            <button
              type="button"
              onClick={onClear}
              className="text-sm font-medium text-surface-subtle underline hover:text-surface-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              Show all recommendations
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function InterventionCard({
  item,
  index,
}: {
  item: InterventionDetail;
  index: number;
}) {
  const signals = item.evidence
    .map(evidenceLabel)
    .filter((label): label is string => label !== null)
    .slice(0, 3);
  return (
    <li className="overflow-hidden rounded-2xl border border-surface-border bg-white shadow-sm">
      <div className="grid gap-5 p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_220px]">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-white tabular-nums">
              {index + 1}
            </span>
            <span className="rounded-full bg-primary-soft px-2.5 py-1 text-xs font-medium capitalize text-primary-strong">
              {category(item.label)}
            </span>
            {item.triggerCount != null ? (
              <span className="text-xs text-surface-subtle">
                Matched {item.triggerCount} prompt
                {item.triggerCount === 1 ? "" : "s"}
              </span>
            ) : null}
          </div>
          <h3 className="mt-3 text-lg font-semibold leading-snug text-surface-foreground">
            {item.title}
          </h3>
          {item.description ? (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-surface-subtle">
              {item.description}
            </p>
          ) : null}
          {item.expectedOutcome ? (
            <div className="mt-5 rounded-xl border border-primary/15 bg-primary-soft/35 px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-primary-strong">
                Expected outcome
              </p>
              <p className="mt-1 text-sm leading-6 text-surface-foreground">
                {item.expectedOutcome}
              </p>
            </div>
          ) : null}
        </div>
        <div className="space-y-5 rounded-xl bg-surface-muted/55 p-4">
          <ScoreBar
            label="Estimated GEO impact"
            value={item.impact}
            tone="impact"
          />
          <ScoreBar
            label="Implementation effort"
            value={item.effort}
            tone="effort"
          />
          <p className="border-t border-surface-border pt-3 text-xs leading-5 text-surface-subtle">
            Scores are estimates from the intervention library, from 1 to 5.
          </p>
        </div>
      </div>
      {item.gapClaims.length > 0 ||
      item.prompts.length > 0 ||
      item.theory ||
      signals.length > 0 ? (
        <div className="grid gap-5 border-t border-surface-border bg-surface-muted/20 px-5 py-4 text-sm sm:px-6 lg:grid-cols-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-surface-subtle">
              Why this action
            </p>
            {item.gapClaims.length > 0 ? (
              <ul className="mt-2 space-y-1.5 text-surface-foreground">
                {item.gapClaims.slice(0, 2).map((claim) => (
                  <li key={claim}>• {claim}</li>
                ))}
              </ul>
            ) : item.theory ? (
              <p className="mt-2 leading-6 text-surface-foreground">
                {item.theory}
              </p>
            ) : null}
            {signals.length > 0 ? (
              <ul className="mt-3 flex flex-wrap gap-2">
                {signals.map((signal) => (
                  <li
                    key={signal}
                    className="rounded-full border border-surface-border bg-white px-2.5 py-1 text-xs text-surface-subtle"
                  >
                    {signal}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          {item.prompts.length > 0 ? (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-surface-subtle">
                Affected prompts
              </p>
              <ul className="mt-2 space-y-1.5 text-surface-foreground">
                {item.prompts.slice(0, 2).map((prompt) => (
                  <li key={prompt}>“{prompt}”</li>
                ))}
              </ul>
              {item.prompts.length > 2 ? (
                <p className="mt-1 text-xs text-surface-subtle">
                  +{item.prompts.length - 2} more prompts
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

export function InterventionsContent({ model }: { model: Model }) {
  const { interventions } = model;
  const actionListRef = useRef<HTMLElement>(null);
  const [selectedPoint, setSelectedPoint] = useState<string | null>(null);
  const [impactFilter, setImpactFilter] = useState<ScoreFilter>("all");
  const [effortFilter, setEffortFilter] = useState<ScoreFilter>("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [page, setPage] = useState(1);
  const categories = [
    ...new Set(interventions.map((item) => category(item.label))),
  ].sort();
  const filtered = interventions
    .map((item, index) => ({ item, index }))
    .filter(
      ({ item }) =>
        matchesScore(item.impact, impactFilter) &&
        matchesScore(item.effort, effortFilter) &&
        (categoryFilter === "all" || category(item.label) === categoryFilter) &&
        (selectedPoint === null ||
          `${item.impact}-${item.effort}` === selectedPoint),
    );
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visible = filtered.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE,
  );
  const changeFilter = () => {
    setPage(1);
    setSelectedPoint(null);
  };
  const clearMapSelection = () => {
    setSelectedPoint(null);
    setPage(1);
  };
  const scrollToList = () => {
    const list = actionListRef.current;
    const scroller = list?.closest("main");
    if (!list || !scroller) return;
    scroller.scrollTo({
      top:
        scroller.scrollTop +
        list.getBoundingClientRect().top -
        scroller.getBoundingClientRect().top -
        24,
      behavior: "smooth",
    });
  };

  useEffect(() => {
    if (window.location.hash !== "#action-table") return;
    window.history.replaceState(
      window.history.state,
      "",
      window.location.pathname + window.location.search,
    );
    window.scrollTo(0, 0);
    scrollToList();
  }, []);
  const quickWins = interventions.filter(
    (item) =>
      item.impact != null &&
      item.impact >= 4 &&
      item.effort != null &&
      item.effort <= 2,
  ).length;
  const matchedPrompts = new Set(interventions.flatMap((item) => item.prompts))
    .size;

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-primary-soft/70 via-white to-white p-6 shadow-sm sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
          From insight to action
        </p>
        <h2 className="mt-2 max-w-3xl text-2xl font-semibold tracking-tight text-surface-foreground sm:text-3xl">
          A focused action plan for {model.domain}
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-surface-subtle">
          These suggestions come from the selected analysis. Compare estimated
          impact with effort, then review the measured gaps and prompts behind
          each action.
        </p>
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          {[
            { value: interventions.length, label: "Recommended actions" },
            { value: quickWins, label: "High impact, low effort" },
            { value: matchedPrompts, label: "Distinct matched prompts" },
          ].map((metric) => (
            <div
              key={metric.label}
              className="rounded-xl border border-white/80 bg-white/85 px-4 py-3 shadow-sm"
            >
              <p className="text-2xl font-semibold tabular-nums text-surface-foreground">
                {metric.value}
              </p>
              <p className="mt-1 text-xs text-surface-subtle">{metric.label}</p>
            </div>
          ))}
        </div>
      </section>

      {interventions.length === 0 ? (
        <section className="rounded-2xl border border-dashed border-surface-border bg-white p-8 text-center">
          <h2 className="font-semibold text-surface-foreground">
            No interventions for this run yet
          </h2>
          <p className="mt-2 text-sm text-surface-subtle">
            This analysis did not produce a matched recommendation.
          </p>
          <Link
            href={`/ai-visibility/drivers?analysis=${model.analysisId}`}
            className="mt-4 inline-flex text-sm font-medium text-primary hover:text-primary-hover"
          >
            Review drivers and gaps
          </Link>
        </section>
      ) : (
        <>
          <ImpactMap
            items={interventions}
            selectedKey={selectedPoint}
            onSelect={(key) => {
              setSelectedPoint(key);
              setImpactFilter("all");
              setEffortFilter("all");
              setCategoryFilter("all");
              setPage(1);
            }}
            onReview={scrollToList}
            onClear={clearMapSelection}
          />
          <section
            ref={actionListRef}
            aria-labelledby="action-list-heading"
            className="scroll-mt-24"
          >
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">
                  Ranked recommendations
                </p>
                <h2
                  id="action-list-heading"
                  className="mt-1 text-xl font-semibold text-surface-foreground"
                >
                  What to do next
                </h2>
                <p className="mt-1 text-sm text-surface-subtle">
                  Ranked by the run’s priority score. Filter by score or
                  category to focus on the actions that matter most.
                </p>
              </div>
              <Link
                href={`/ai-visibility/drivers?analysis=${model.analysisId}`}
                className="text-sm font-medium text-primary hover:text-primary-hover"
              >
                Explore drivers & gaps →
              </Link>
            </div>
            <div className="mb-4 flex flex-wrap gap-3">
              <FilterDropdown
                label="Impact"
                value={impactFilter}
                options={IMPACT_OPTIONS}
                onChange={(next) => {
                  changeFilter();
                  setImpactFilter(next as ScoreFilter);
                }}
              />
              <FilterDropdown
                label="Effort"
                value={effortFilter}
                options={EFFORT_OPTIONS}
                onChange={(next) => {
                  changeFilter();
                  setEffortFilter(next as ScoreFilter);
                }}
              />
              <FilterDropdown
                label="Category"
                value={categoryFilter}
                options={[
                  { value: "all", label: "All categories" },
                  ...categories.map((name) => ({ value: name, label: name })),
                ]}
                onChange={(next) => {
                  changeFilter();
                  setCategoryFilter(next);
                }}
              />
            </div>
            <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
              <p role="status" className="text-surface-subtle">
                {filtered.length} of {interventions.length} recommendations
                shown
              </p>
              {selectedPoint ? (
                <button
                  type="button"
                  onClick={clearMapSelection}
                  className="font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  Show all recommendations
                </button>
              ) : null}
            </div>
            {visible.length > 0 ? (
              <ol className="space-y-4" aria-label="Ranked recommendations">
                {visible.map(({ item, index }) => (
                  <InterventionCard
                    key={`${item.id}-${index}`}
                    item={item}
                    index={index}
                  />
                ))}
              </ol>
            ) : (
              <p className="rounded-2xl border border-surface-border bg-white px-4 py-8 text-center text-sm text-surface-subtle shadow-sm">
                No recommendations match these filters.
              </p>
            )}
            {totalPages > 1 ? (
              <nav
                aria-label="Recommendations pagination"
                className="mt-4 flex items-center justify-between gap-3 text-sm"
              >
                <button
                  type="button"
                  disabled={currentPage === 1}
                  onClick={() => setPage(currentPage - 1)}
                  className="rounded-lg border border-surface-border bg-white px-3 py-2 text-surface-foreground hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50"
                >
                  Previous
                </button>
                <span className="tabular-nums text-surface-subtle">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  type="button"
                  disabled={currentPage === totalPages}
                  onClick={() => setPage(currentPage + 1)}
                  className="rounded-lg border border-surface-border bg-white px-3 py-2 text-surface-foreground hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50"
                >
                  Next
                </button>
              </nav>
            ) : null}
          </section>
        </>
      )}
    </div>
  );
}

export default function InterventionsClient() {
  return (
    <AnalysisBoundSubpage title="Recommended interventions">
      {(analysis) => (
        <InterventionsContent model={interventionsFromAnalysis(analysis)} />
      )}
    </AnalysisBoundSubpage>
  );
}
