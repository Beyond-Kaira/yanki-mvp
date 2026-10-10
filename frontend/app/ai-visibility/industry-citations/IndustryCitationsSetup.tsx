'use client'

import { useEffect, useState } from 'react'
import PageContainer from '@/components/shell/PageContainer'
import {
  fetchIndustryRanking,
  fetchIndustrySectors,
  type IndustryRanking,
  type IndustrySector,
} from '@/lib/industry-citations'

const REASONS: Record<string, string> = {
  brand_probe: 'Brand-specific questions',
  unknown_provenance: 'Live origin not verified',
  mock: 'Demo records',
  simulated: 'Simulated records',
  mock_or_simulated: 'Demo or simulated records',
  analysis_not_complete: 'Incomplete analyses',
  failed_or_missing_answer: 'Failed or missing answers',
  missing_question: 'Missing questions',
  missing_evidence: 'Missing evidence',
  missing_inline_marker: 'Missing citation markers in answers',
  source_url_mismatch: 'Source URL mismatch',
  unmatched_result_rank: 'Unmatched search result',
  invalid_result_rank: 'Invalid search result rank',
  invalid_source_url: 'Invalid source URL',
  malformed_citation: 'Malformed citation',
}

export default function IndustryCitationsSetup() {
  const [sectors, setSectors] = useState<IndustrySector[]>([])
  const [sector, setSector] = useState('')
  const [offset, setOffset] = useState(0)
  const [report, setReport] = useState<IndustryRanking | null>(null)
  const [loadingSectors, setLoadingSectors] = useState(true)
  const [loading, setLoading] = useState(false)
  const [sectorError, setSectorError] = useState('')
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoadingSectors(true)
    setSectorError('')
    fetchIndustrySectors(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setSectors(items)
      })
      .catch((cause) => {
        if (!controller.signal.aborted)
          setSectorError(
            cause instanceof Error
              ? cause.message
              : 'Could not load industries.',
          )
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingSectors(false)
      })
    return () => controller.abort()
  }, [retry])

  useEffect(() => {
    if (!sector) return
    const controller = new AbortController()
    setLoading(true)
    setError('')
    setReport(null)
    fetchIndustryRanking(sector, offset, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setReport(value)
      })
      .catch((cause) => {
        if (!controller.signal.aborted)
          setError(
            cause instanceof Error ? cause.message : 'Could not load ranking.',
          )
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [sector, offset, retry])

  return (
    <PageContainer>
      <p className="mb-2 text-xs font-medium uppercase tracking-wider text-surface-subtle">
        Industry research
      </p>
      <h1 className="text-2xl font-semibold tracking-tight">
        Top Cited Pages for Your Industry
      </h1>
      <p className="mt-3 max-w-3xl text-sm text-surface-subtle">
        See which websites AI answers cite most often for companies in your
        industry. Choose an industry, compare websites, then expand a row to
        explore the cited pages.
      </p>
      <div className="mt-6 rounded-xl border border-surface-border bg-white p-5">
        <label htmlFor="industry" className="block text-sm font-medium">
          Industry
        </label>
        <select
          id="industry"
          value={sector}
          disabled={loadingSectors || !!sectorError}
          onChange={(event) => {
            setSector(event.target.value)
            setOffset(0)
            setReport(null)
            setError('')
          }}
          className="mt-2 w-full rounded-lg border border-surface-border bg-white px-3 py-2.5 text-sm sm:max-w-md"
        >
          <option value="">Select an industry</option>
          {sectors.map((item) => (
            <option key={item.sector} value={item.sector}>
              {item.sector} ({item.record_count} records)
            </option>
          ))}
        </select>
        <p className="mt-3 text-sm text-surface-subtle">
          Based on existing GEO analyses across all organizations. The record
          count includes answers that may not yet qualify for the ranking.
        </p>
      </div>
      {loadingSectors ? (
        <p role="status" className="mt-5 text-sm">
          Loading industries…
        </p>
      ) : null}
      {!loadingSectors && !sectorError && sectors.length === 0 ? (
        <p role="status" className="mt-5 text-sm">
          No industry data is available yet.
        </p>
      ) : null}
      {sectorError || error ? (
        <div role="alert" className="mt-5 text-sm text-warning-strong">
          <p>{sectorError || error}</p>
          <button
            type="button"
            onClick={() => setRetry((value) => value + 1)}
            className="mt-2 underline"
          >
            Try again
          </button>
        </div>
      ) : null}
      {sector && loading ? (
        <p role="status" className="mt-5 text-sm">
          Loading ranking…
        </p>
      ) : null}
      {report && sector ? (
        <>
          <section
            className="mt-6 rounded-xl border border-surface-border bg-white p-5"
            aria-label="Data readiness"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold">
                  Data available for this industry
                </h2>
                <p className="mt-1 text-sm text-surface-subtle">
                  Only eligible answers are used to calculate the ranking.
                </p>
              </div>
              <span
                className={`rounded-full px-3 py-1 text-xs font-medium ${report.eligible_responses ? 'bg-teal-50 text-teal-800' : 'bg-amber-50 text-amber-800'}`}
              >
                {report.eligible_responses
                  ? 'Ranking available'
                  : 'No eligible answers yet'}
              </span>
            </div>
            <div className="mt-5 grid gap-4 sm:grid-cols-3">
              {[
                [report.candidate_responses, 'Stored records'],
                [report.eligible_responses, 'Answers included'],
                [
                  Object.values(report.excluded_responses).reduce(
                    (sum, n) => sum + n,
                    0,
                  ),
                  'Answers excluded',
                ],
              ].map(([value, label]) => (
                <div key={label}>
                  <p className="text-2xl font-semibold tabular-nums">{value}</p>
                  <p className="mt-1 text-sm text-surface-subtle">{label}</p>
                </div>
              ))}
            </div>
            <div
              className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100"
              aria-hidden="true"
            >
              <div
                className="h-full rounded-full bg-teal-600"
                style={{
                  width: `${report.candidate_responses ? (100 * report.eligible_responses) / report.candidate_responses : 0}%`,
                }}
              />
            </div>
            {Object.keys(report.excluded_responses).length > 0 && (
              <div className="mt-4 border-t border-surface-border pt-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-surface-subtle">
                  Why some answers are excluded
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {Object.entries(report.excluded_responses).map(
                    ([reason, count]) => (
                      <span
                        key={reason}
                        className="rounded-lg bg-slate-50 px-3 py-2 text-sm"
                      >
                        {REASONS[reason] || reason}
                        <strong className="ml-2 tabular-nums">{count}</strong>
                      </span>
                    ),
                  )}
                </div>
                {report.excluded_responses.unknown_provenance ? (
                  <p className="mt-3 text-xs text-surface-subtle">
                    Unverified does not mean simulated: these records do not
                    have enough metadata to confirm a live run.
                  </p>
                ) : null}
              </div>
            )}
          </section>
          <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              [
                report.eligible_responses,
                'Eligible answers',
                'The base used for coverage',
              ],
              [
                report.distinct_questions,
                'Distinct questions',
                'Repeated question text counted once',
              ],
              [
                report.site_count,
                'Cited websites',
                'Separate hostnames in the ranking',
              ],
              [report.page_count, 'Cited pages', 'Unique verified source URLs'],
            ].map(([value, label, description]) => (
              <div
                key={label}
                className="rounded-xl border border-surface-border bg-white p-4"
              >
                <p className="text-2xl font-semibold">{value}</p>
                <p className="mt-1 text-sm text-surface-subtle">{label}</p>
                <p className="mt-2 text-xs text-surface-subtle">
                  {description}
                </p>
              </div>
            ))}
          </div>
          <details className="mt-5 rounded-lg border border-surface-border p-4 text-sm">
            <summary className="cursor-pointer font-medium">
              How this ranking is calculated ·{' '}
              {Object.values(report.rejected_citations).reduce(
                (sum, n) => sum + n,
                0,
              )}{' '}
              rejected citations
            </summary>
            <p className="mt-3">
              This report uses company sector labels; individual questions can
              cover related products and topics. Customer identities and private
              question/answer text are not shown.
            </p>
            <p className="mt-3 text-surface-subtle">{report.methodology}</p>
            {Object.entries(report.rejected_citations).map(
              ([reason, count]) => (
                <p key={reason} className="mt-2">
                  Rejected citations — {REASONS[reason] || reason}: {count}
                </p>
              ),
            )}
          </details>
          {report.eligible_responses === 0 ? (
            <p
              role="status"
              className="mt-6 rounded-lg border border-surface-border p-5"
            >
              {report.candidate_responses
                ? 'Records exist for this industry, but none currently meet the live-data and evidence requirements.'
                : 'No records are available for this industry yet.'}
            </p>
          ) : report.site_count === 0 ? (
            <p role="status" className="mt-6">
              Eligible answers exist, but no citations passed verification.
            </p>
          ) : (
            <>
              <h2 className="mt-8 text-lg font-semibold">
                Most cited websites
              </h2>
              <p className="mt-2 text-sm text-surface-subtle">
                Ranked by citing answers, then distinct questions. Coverage
                shows how many of the {report.eligible_responses} eligible
                answers cite each website. Click a website to explore its pages.
              </p>
              <div className="mt-4 space-y-3">
                {report.sites.map((site, index) => (
                  <details
                    key={report.sector + ':' + site.domain}
                    className="group overflow-hidden rounded-xl border border-surface-border bg-white open:border-teal-600"
                  >
                    <summary className="flex cursor-pointer list-none flex-col gap-4 p-4 transition-colors hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-600 md:flex-row md:items-center [&::-webkit-details-marker]:hidden">
                      <span className="min-w-0 flex-1">
                        <span className="break-all font-semibold">
                          {report.offset + index + 1}. {site.domain}
                        </span>
                        <span className="mt-1 block text-xs text-surface-subtle">
                          {site.page_count} cited{' '}
                          {site.page_count === 1 ? 'page' : 'pages'}{' '}
                          <span
                            aria-hidden="true"
                            className="ml-1 inline-block transition-transform group-open:rotate-90"
                          >
                            ›
                          </span>
                        </span>
                      </span>
                      <span className="grid shrink-0 grid-cols-3 gap-5 md:w-72">
                        <span>
                          <strong className="block text-lg tabular-nums">
                            {site.response_count}
                          </strong>
                          <span className="text-xs text-surface-subtle">
                            Citing answers
                          </span>
                        </span>
                        <span>
                          <strong className="block text-lg tabular-nums">
                            {site.question_count}
                          </strong>
                          <span className="text-xs text-surface-subtle">
                            Questions
                          </span>
                        </span>
                        <span>
                          <strong className="block text-lg tabular-nums">
                            {site.response_coverage}%
                          </strong>
                          <span className="text-xs text-surface-subtle">
                            Coverage
                          </span>
                          <span
                            className="mt-1 block h-1 rounded-full bg-slate-100"
                            aria-hidden="true"
                          >
                            <span
                              className="block h-1 rounded-full bg-teal-600"
                              style={{ width: `${site.response_coverage}%` }}
                            />
                          </span>
                        </span>
                      </span>
                    </summary>
                    <div className="border-t border-surface-border bg-slate-50/60 p-4">
                      <p className="text-xs font-medium text-surface-subtle">
                        Citing answers by AI model
                      </p>
                      <p className="mt-2 text-xs text-surface-subtle">
                        {Object.entries(site.model_counts)
                          .map(
                            ([model, count]) =>
                              model + ': ' + count + ' answers',
                          )
                          .join(' · ')}
                      </p>
                      <ul className="mt-4 space-y-3 border-t border-surface-border pt-4">
                        {site.pages.map((page) => (
                          <li
                            key={page.url}
                            className="rounded-lg border border-surface-border bg-white p-3"
                          >
                            <a
                              href={page.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="break-all text-sm underline"
                            >
                              {page.url}
                            </a>
                            <p className="mt-1 text-xs text-surface-subtle">
                              {page.response_count} answers ·{' '}
                              {page.question_count} questions ·{' '}
                              {page.response_coverage}% coverage
                            </p>
                          </li>
                        ))}
                      </ul>
                      {site.page_count > site.pages.length ? (
                        <p className="mt-3 text-sm">
                          Showing the first {site.pages.length} of{' '}
                          {site.page_count} pages.
                        </p>
                      ) : null}
                    </div>
                  </details>
                ))}
              </div>
              <div className="mt-5 flex items-center gap-4 text-sm">
                <button
                  type="button"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - 25))}
                  className="rounded-lg border border-surface-border px-3 py-2 disabled:opacity-40"
                >
                  Previous
                </button>
                <span>
                  {report.offset + 1}–
                  {Math.min(
                    report.offset + report.sites.length,
                    report.site_count,
                  )}{' '}
                  of {report.site_count} websites
                </span>
                <button
                  type="button"
                  disabled={
                    offset + 25 >= report.site_count || offset + 25 > 10000
                  }
                  onClick={() => setOffset(offset + 25)}
                  className="rounded-lg border border-surface-border px-3 py-2 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </>
          )}
        </>
      ) : null}
    </PageContainer>
  )
}
