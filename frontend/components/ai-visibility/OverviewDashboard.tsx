"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import {
  IconCheck,
  IconChevron,
  IconInfo,
  IconShield,
} from "@/components/shell/icons";
import type { AiOverviewModel } from "@/lib/ai-overview";
import MentionShare from "@/components/insights/MentionShare";
import MultiLlmComparison from "@/components/insights/MultiLlmComparison";
import NamingOrder from "@/components/insights/NamingOrder";
import OverviewInsightCards from "@/components/ai-visibility/OverviewInsightCards";

interface OverviewDashboardProps {
  model: AiOverviewModel;
}

function MetricCard({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-surface-border bg-surface p-5 shadow-sm">
      <div className="mb-3 flex items-center gap-1.5 text-sm text-surface-subtle">
        <span>{label}</span>
        <IconInfo className="h-3.5 w-3.5" />
      </div>
      {children}
    </section>
  );
}

function Donut({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  const r = 36;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - clamped / 100);
  return (
    <svg viewBox="0 0 96 96" className="h-20 w-20" aria-hidden>
      <circle
        cx="48"
        cy="48"
        r={r}
        fill="none"
        className="stroke-surface-border"
        strokeWidth="10"
      />
      <circle
        cx="48"
        cy="48"
        r={r}
        fill="none"
        className="stroke-primary"
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={offset}
        transform="rotate(-90 48 48)"
      />
    </svg>
  );
}

function Sparkline({ points }: { points: number[] }) {
  const w = 120;
  const h = 36;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const d = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - ((p - min) / span) * (h - 4) - 2;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-9 w-28" aria-hidden>
      <path d={d} fill="none" className="stroke-primary" strokeWidth="2" />
    </svg>
  );
}

export default function OverviewDashboard({ model }: OverviewDashboardProps) {
  const geo = model.geoScore;
  const citePct =
    model.citeRate == null ? null : Math.round(model.citeRate * 1000) / 10;
  const reliability =
    model.reliability == null
      ? null
      : Math.round(model.reliability * 100) / 100;

  return (
    <div className="mx-auto max-w-6xl px-6 py-8 sm:px-8">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-surface-foreground">
          AI Visibility
        </h1>
        <p className="mt-1 text-sm text-surface-subtle">
          Overview ·{" "}
          <span className="font-medium text-primary">{model.domain}</span>
          {model.isSample ? (
            <span className="ml-2 rounded-full bg-warning-soft px-2 py-0.5 text-[11px] font-medium text-warning-strong">
              Sample preview
            </span>
          ) : null}
        </p>
      </header>

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard label="GEO score">
          <div className="flex items-center justify-between gap-3">
            <div>
              {geo == null ? (
                <p className="text-3xl font-semibold text-surface-subtle">
                  N/A
                </p>
              ) : (
                <p className="text-3xl font-semibold tabular-nums">
                  {geo}
                  <span className="text-lg font-normal text-surface-subtle">
                    {" "}
                    /100
                  </span>
                </p>
              )}
              <p className="mt-2 text-xs font-medium text-success">
                {model.isSample
                  ? "+6 vs last 7 days"
                  : "From latest measured run"}
              </p>
            </div>
            {geo != null ? <Donut value={geo} /> : null}
          </div>
        </MetricCard>

        <MetricCard label="Cite rate">
          <div className="flex items-end justify-between gap-3">
            <div>
              {citePct == null ? (
                <p className="text-3xl font-semibold text-surface-subtle">
                  N/A
                </p>
              ) : (
                <p className="text-3xl font-semibold tabular-nums">
                  {citePct}%
                </p>
              )}
              <p className="mt-2 text-xs font-medium text-success">
                {model.isSample ? "+3 pp vs last 7 days" : "Mentions / answers"}
              </p>
            </div>
            <Sparkline points={[8, 10, 9, 12, 14, 13, 18]} />
          </div>
        </MetricCard>

        <MetricCard label="Reliability">
          <div className="flex items-end justify-between gap-3">
            <div>
              {reliability == null ? (
                <p className="text-3xl font-semibold text-surface-subtle">
                  N/A
                </p>
              ) : (
                <p className="text-3xl font-semibold tabular-nums">
                  {reliability.toFixed(2)}
                </p>
              )}
              <p className="mt-2 text-xs font-medium text-success">
                {model.isSample ? "+0.06 vs last 7 days" : "Claim audit score"}
              </p>
            </div>
            <Sparkline points={[0.55, 0.6, 0.58, 0.66, 0.7, 0.72, 0.77]} />
          </div>
        </MetricCard>
      </div>

      {model.insights ? (
        <OverviewInsightCards
          insights={model.insights}
          analysisId={model.analysisId}
        />
      ) : null}

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <section className="rounded-2xl border border-surface-border bg-surface p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-1.5 text-sm font-medium text-surface-foreground">
            <span>Citations from Tavily</span>
            <IconInfo className="h-3.5 w-3.5 text-surface-subtle" />
          </div>
          {model.citations.length === 0 ? (
            <p className="rounded-xl border border-dashed border-surface-border px-3 py-8 text-center text-sm text-surface-subtle">
              No citations recorded for this run yet.
            </p>
          ) : (
            <div className="overflow-hidden rounded-xl border border-surface-border">
              <table className="w-full text-left text-sm">
                <thead className="bg-surface-muted text-xs uppercase tracking-wide text-surface-subtle">
                  <tr>
                    <th className="px-3 py-2 font-medium">Domain</th>
                    <th className="px-3 py-2 text-right font-medium">
                      Citations
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {model.citations.map((row) => (
                    <tr
                      key={row.domain}
                      className="border-t border-surface-border"
                    >
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-2">
                          <span
                            className="flex h-6 w-6 items-center justify-center rounded-full bg-primary-soft text-[10px] font-semibold text-primary-strong"
                            aria-hidden
                          >
                            {row.domain.slice(0, 1).toUpperCase()}
                          </span>
                          <span className="text-surface-foreground">
                            {row.domain}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-surface-subtle">
                        {row.count}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Link
            href={
              model.analysisId
                ? `/ai-visibility/citations?analysis=${model.analysisId}`
                : "/ai-visibility/citations"
            }
            className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary hover:text-primary-hover"
          >
            View all citations
            <IconChevron className="h-4 w-4" />
          </Link>
        </section>

        <section className="rounded-2xl border border-surface-border bg-surface p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-1.5 text-sm font-medium text-surface-foreground">
            <span>Recommended interventions</span>
            <IconInfo className="h-3.5 w-3.5 text-surface-subtle" />
          </div>
          {model.interventions.length === 0 ? (
            <p className="rounded-xl border border-dashed border-surface-border px-3 py-8 text-center text-sm text-surface-subtle">
              No interventions for this run yet.
            </p>
          ) : (
            <ul className="divide-y divide-surface-border rounded-xl border border-surface-border">
              {model.interventions.map((item) => (
                <li
                  key={item.title}
                  className="flex items-center gap-3 px-3 py-3 text-sm"
                >
                  <span className="text-primary">
                    <IconCheck className="h-5 w-5" />
                  </span>
                  <span className="flex-1 text-surface-foreground">
                    {item.title}
                  </span>
                  <IconChevron className="h-4 w-4 text-surface-subtle" />
                </li>
              ))}
            </ul>
          )}
          <Link
            href={
              model.analysisId
                ? `/ai-visibility/drivers?analysis=${model.analysisId}`
                : "/ai-visibility/drivers"
            }
            className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary hover:text-primary-hover"
          >
            View all interventions
            <IconChevron className="h-4 w-4" />
          </Link>
        </section>
      </div>

      {model.insights ? (
        <div className="mt-8 space-y-5">
          <MultiLlmComparison engines={model.insights.engines} />
          <MentionShare
            brand={model.insights.brand}
            engines={model.insights.engines}
          />
          <NamingOrder engines={model.insights.engines} />
        </div>
      ) : null}

      <p className="mt-8 flex items-center gap-2 text-xs text-surface-subtle">
        <IconShield className="h-3.5 w-3.5" />
        Data from measured GEO audit
        {model.analysisId ? ` · ${model.analysisId.slice(0, 8)}…` : ""}
      </p>
    </div>
  );
}
