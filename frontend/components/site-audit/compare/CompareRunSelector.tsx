"use client";

import { useEffect, useRef, useState } from "react";
import type { SiteAuditRunSummary } from "@/lib/contracts";
import {
  MAX_COMPARED_RUNS,
  MIN_COMPARED_RUNS,
  runLabel,
  totalIssues,
} from "./compareUtils";

/**
 * Which crawls to compare.
 *
 * A listbox rather than a set of checkboxes in the page: the list grows with
 * every re-run, and a control that gets taller forever pushes the charts the
 * customer came for off the screen. Follows the same open/close contract as the
 * org switcher in the shell — click outside or press Escape.
 *
 * The bounds are enforced by disabling options rather than by refusing the
 * click: an option that visibly cannot be chosen, with the reason on it, beats
 * one that silently does nothing.
 */
export default function CompareRunSelector({
  runs,
  selectedIds,
  onChange,
}: {
  runs: SiteAuditRunSummary[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const atMax = selectedIds.length >= MAX_COMPARED_RUNS;
  const atMin = selectedIds.length <= MIN_COMPARED_RUNS;

  function toggle(runId: string) {
    const selected = selectedIds.includes(runId);
    if (selected && atMin) return;
    if (!selected && atMax) return;
    onChange(
      selected
        ? selectedIds.filter((id) => id !== runId)
        : // Keep newest-first, so the columns never reorder under the customer.
          runs
            .filter((run) => run.id === runId || selectedIds.includes(run.id))
            .map((run) => run.id),
    );
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex min-h-[44px] items-center gap-2 rounded-lg border border-surface-subtle bg-white px-4 text-sm font-medium text-surface-foreground transition-colors hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <span>
          Comparing {selectedIds.length} of {runs.length} crawls
        </span>
        <svg
          viewBox="0 0 24 24"
          className="h-4 w-4 shrink-0 text-surface-subtle"
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
          role="listbox"
          aria-multiselectable="true"
          aria-label="Crawls to compare"
          className="absolute left-0 top-full z-40 mt-1 max-h-[min(60vh,360px)] w-[min(24rem,90vw)] overflow-y-auto rounded-lg border border-surface-border bg-surface py-1 shadow-lg"
        >
          {runs.map((run) => {
            const selected = selectedIds.includes(run.id);
            const blocked = selected ? atMin : atMax;
            return (
              <li key={run.id} role="option" aria-selected={selected}>
                <button
                  type="button"
                  onClick={() => toggle(run.id)}
                  disabled={blocked}
                  title={
                    blocked
                      ? selected
                        ? `Keep at least ${MIN_COMPARED_RUNS} crawls selected.`
                        : `Deselect one first — at most ${MAX_COMPARED_RUNS} crawls fit.`
                      : undefined
                  }
                  className={`flex w-full items-start gap-3 px-3 py-2.5 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50 ${
                    selected ? "bg-primary-soft" : "hover:bg-surface-muted"
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[10px] font-bold ${
                      selected
                        ? "border-primary bg-primary text-white"
                        : "border-surface-subtle"
                    }`}
                  >
                    {selected ? "✓" : ""}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium text-surface-foreground">
                      {runLabel(run)}
                    </span>
                    <span className="block text-xs text-surface-subtle">
                      {run.pages_crawled} pages · {totalIssues(run)} issues ·{" "}
                      {run.health_score == null
                        ? "not scorable"
                        : `${run.health_score}% health`}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
