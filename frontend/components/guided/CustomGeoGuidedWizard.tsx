'use client'

import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import Button from '@/components/Button'
import CustomFormField, {
  CustomFieldShell,
  customFieldDescribedBy,
  customFieldInputClass,
} from '@/components/CustomFormField'
import {
  executePromptsAndScore,
  patchAnalysisKyc,
  patchAnalysisPrompts,
  ApiError,
} from '@/lib/api'
import { analysisDomain } from '@/lib/ai-visibility-data'
import { mergeAnalysis } from '@/lib/analysis-bundle'
import type { Analysis, KYC } from '@/lib/contracts'
import {
  attributePromptApiError,
  countNewUserPrompts,
  draftToKycPatch,
  draftsToPatchItems,
  firstPromptErrorIndex,
  kycToDraft,
  MAX_USER_PROMPTS,
  PROMPT_CATEGORIES,
  promptsToDrafts,
  validatePromptDrafts,
  type KycDraft,
  type PromptDraft,
} from '@/lib/guided-analysis'

type WizardStep = 'profile' | 'prompts' | 'measure'

const STEPS: { id: WizardStep; label: string }[] = [
  { id: 'profile', label: 'Company profile' },
  { id: 'prompts', label: 'Prompts' },
  { id: 'measure', label: 'Measure' },
]

function emptyKyc(): KycDraft {
  return {
    company: '',
    description: '',
    industry: '',
    category: '',
    aliases: '',
    products: '',
    services: '',
    keywords: '',
    use_cases: '',
    locations: '',
    competitors: '',
  }
}

export default function CustomGeoGuidedWizard({
  analysis,
  onAnalysisUpdated,
  onMeasureStarted,
}: {
  analysis: Analysis
  onAnalysisUpdated: (analysis: Analysis) => void
  onMeasureStarted: () => void
}) {
  const initialKyc = useMemo(
    () =>
      analysis.result.kyc
        ? kycToDraft(analysis.result.kyc)
        : emptyKyc(),
    [analysis.result.kyc],
  )
  const [step, setStep] = useState<WizardStep>('profile')
  const [kycDraft, setKycDraft] = useState<KycDraft>(initialKyc)
  const [kycBaseline, setKycBaseline] = useState<KycDraft>(initialKyc)
  const [promptDrafts, setPromptDrafts] = useState<PromptDraft[]>(() =>
    promptsToDrafts(analysis.result.prompts),
  )
  const [promptErrors, setPromptErrors] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const promptRowRefs = useRef<(HTMLLIElement | null)[]>([])
  const scrollToPromptIndex = useRef<number | null>(null)

  const domain = analysisDomain(analysis)
  const newUserPrompts = countNewUserPrompts(promptDrafts)

  useLayoutEffect(() => {
    const index = scrollToPromptIndex.current
    if (index === null) return
    scrollToPromptIndex.current = null
    promptRowRefs.current[index]?.scrollIntoView({
      behavior: 'smooth',
      block: 'center',
    })
  }, [promptErrors])

  function showPromptErrors(errors: Record<number, string>) {
    const first = firstPromptErrorIndex(errors)
    if (first !== null) {
      scrollToPromptIndex.current = first
    }
    setPromptErrors(errors)
    setError(null)
  }

  function clearPromptErrorAt(index: number) {
    setPromptErrors((current) => {
      if (current[index] === undefined) return current
      const next = { ...current }
      delete next[index]
      return next
    })
  }

  function updatePromptDraft(
    index: number,
    updater: (draft: PromptDraft) => PromptDraft,
  ) {
    clearPromptErrorAt(index)
    setPromptDrafts((rows) =>
      rows.map((row, rowIndex) => (rowIndex === index ? updater(row) : row)),
    )
  }

  function updateKycField<K extends keyof KycDraft>(key: K, value: KycDraft[K]) {
    setKycDraft((current) => ({ ...current, [key]: value }))
  }

  async function saveProfile(andContinue: boolean) {
    setError(null)
    const patch = draftToKycPatch(kycDraft, kycBaseline)
    setBusy(true)
    try {
      if (Object.keys(patch).length > 0) {
        const profile = await patchAnalysisKyc(analysis.id, patch)
        const merged = mergeAnalysis(analysis, {
          kyc: { kyc: profile.kyc as KYC },
          prompts: { prompts: profile.prompts },
        })
        onAnalysisUpdated(merged)
        const nextDraft = profile.kyc ? kycToDraft(profile.kyc as KYC) : kycDraft
        setKycDraft(nextDraft)
        setKycBaseline(nextDraft)
        setPromptDrafts(promptsToDrafts(profile.prompts))
      }
      if (andContinue) {
        setStep('prompts')
      }
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Could not save the company profile.',
      )
    } finally {
      setBusy(false)
    }
  }

  async function savePrompts(andContinue: boolean) {
    setError(null)
    setPromptErrors({})

    const validationErrors = validatePromptDrafts(
      promptDrafts,
      analysis.result.kyc,
    )
    if (Object.keys(validationErrors).length > 0) {
      showPromptErrors(validationErrors)
      return
    }

    setBusy(true)
    try {
      const updated = await patchAnalysisPrompts(
        analysis.id,
        draftsToPatchItems(promptDrafts),
      )
      const merged = mergeAnalysis(analysis, {
        prompts: { prompts: updated.prompts },
      })
      onAnalysisUpdated(merged)
      setPromptDrafts(promptsToDrafts(updated.prompts))
      setPromptErrors({})
      if (andContinue) {
        setStep('measure')
      }
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : 'Could not save the prompt set.'
      const attributed = attributePromptApiError(
        message,
        promptDrafts,
        analysis.result.kyc,
      )
      if (Object.keys(attributed).length > 0) {
        showPromptErrors(attributed)
      } else {
        setError(message)
      }
    } finally {
      setBusy(false)
    }
  }

  async function runMeasure() {
    setError(null)
    setBusy(true)
    try {
      await executePromptsAndScore(analysis.id)
      onMeasureStarted()
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Could not start measurement.',
      )
      setBusy(false)
    }
  }

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <p className="text-sm font-medium text-primary-strong">Guided analysis</p>
        <h1 className="text-2xl font-semibold tracking-tight">
          Review before measuring
        </h1>
        <p className="text-sm text-surface-subtle">
          We crawled{' '}
          <span className="font-medium text-surface-foreground">{domain}</span>{' '}
          and drafted a company profile plus buyer questions. Edit anything that
          looks wrong, then run the expensive measurement step once.
        </p>
      </header>

      <nav aria-label="Review steps">
        <ol className="flex flex-wrap gap-2">
          {STEPS.map((item, index) => {
            const active = item.id === step
            const done =
              (item.id === 'profile' && (step === 'prompts' || step === 'measure')) ||
              (item.id === 'prompts' && step === 'measure')
            return (
              <li key={item.id}>
                <span
                  className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium ${
                    active
                      ? 'bg-primary text-white'
                      : done
                        ? 'bg-success-soft text-success-strong'
                        : 'bg-surface-muted text-surface-subtle'
                  }`}
                >
                  <span aria-hidden="true">{index + 1}</span>
                  {item.label}
                </span>
              </li>
            )
          })}
        </ol>
      </nav>

      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}

      {step === 'profile' ? (
        <section className="space-y-6 rounded-2xl border border-surface-border bg-surface p-6">
          <h2 className="text-lg font-semibold">Company profile</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <CustomFormField
              id="guided-company"
              label="Company"
              value={kycDraft.company}
              onChange={(event) => updateKycField('company', event.target.value)}
              disabled={busy}
            />
            <CustomFormField
              id="guided-category"
              label="Category"
              value={kycDraft.category}
              onChange={(event) => updateKycField('category', event.target.value)}
              disabled={busy}
              hint="The buying category your prompts are built from."
            />
            <CustomFormField
              id="guided-industry"
              label="Industry"
              value={kycDraft.industry}
              onChange={(event) => updateKycField('industry', event.target.value)}
              disabled={busy}
            />
            <CustomFormField
              id="guided-locations"
              label="Locations"
              value={kycDraft.locations}
              onChange={(event) => updateKycField('locations', event.target.value)}
              disabled={busy}
              hint="Comma-separated."
            />
          </div>
          <CustomFieldShell id="guided-description" label="Description">
            <textarea
              id="guided-description"
              rows={3}
              value={kycDraft.description}
              onChange={(event) => updateKycField('description', event.target.value)}
              disabled={busy}
              className={customFieldInputClass(false)}
              aria-describedby={customFieldDescribedBy('guided-description')}
            />
          </CustomFieldShell>
          <div className="grid gap-4 sm:grid-cols-2">
            <CustomFormField
              id="guided-keywords"
              label="Keywords"
              value={kycDraft.keywords}
              onChange={(event) => updateKycField('keywords', event.target.value)}
              disabled={busy}
              hint="Comma-separated."
            />
            <CustomFormField
              id="guided-use-cases"
              label="Use cases"
              value={kycDraft.use_cases}
              onChange={(event) => updateKycField('use_cases', event.target.value)}
              disabled={busy}
              hint="Comma-separated."
            />
            <CustomFormField
              id="guided-products"
              label="Products"
              value={kycDraft.products}
              onChange={(event) => updateKycField('products', event.target.value)}
              disabled={busy}
              hint="Comma-separated."
            />
            <CustomFormField
              id="guided-services"
              label="Services"
              value={kycDraft.services}
              onChange={(event) => updateKycField('services', event.target.value)}
              disabled={busy}
              hint="Comma-separated."
            />
            <CustomFormField
              id="guided-competitors"
              label="Competitors"
              value={kycDraft.competitors}
              onChange={(event) => updateKycField('competitors', event.target.value)}
              disabled={busy}
              hint="Comma-separated."
            />
            <CustomFormField
              id="guided-aliases"
              label="Aliases"
              value={kycDraft.aliases}
              onChange={(event) => updateKycField('aliases', event.target.value)}
              disabled={busy}
              hint="Comma-separated."
            />
          </div>
          <div className="flex flex-wrap gap-3">
            <Button
              type="button"
              loading={busy}
              onClick={() => saveProfile(true)}
            >
              Save and continue
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={busy}
              onClick={() => setStep('prompts')}
            >
              Continue without saving
            </Button>
          </div>
        </section>
      ) : null}

      {step === 'prompts' ? (
        <section className="space-y-6 rounded-2xl border border-surface-border bg-surface p-6">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold">Prompts</h2>
            <p className="text-sm text-surface-subtle">
              These are the questions we will ask AI engines. Category prompts
              must not name your brand. You can add up to {MAX_USER_PROMPTS}{' '}
              custom prompts.
            </p>
          </div>
          <ul className="space-y-4">
            {promptDrafts.map((draft, index) => {
              const locked = draft.locked || draft.editable === false
              const rowError = promptErrors[index]
              const rowErrorId = `guided-prompt-${index}-error`
              return (
                <li
                  key={draft.id ?? `new-${index}`}
                  ref={(element) => {
                    promptRowRefs.current[index] = element
                  }}
                  id={`guided-prompt-${index}`}
                  className={`space-y-3 rounded-xl border p-4 transition-colors ${
                    rowError
                      ? 'border-danger bg-danger-soft/40 ring-2 ring-danger/25'
                      : 'border-surface-border bg-surface-muted/40'
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-medium uppercase tracking-wide text-surface-subtle">
                      {draft.source ?? 'draft'}
                      {locked ? ' · locked' : ''}
                      {rowError ? (
                        <span className="ml-2 normal-case text-danger-strong">
                          · needs attention
                        </span>
                      ) : null}
                    </span>
                    {!locked ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={busy}
                        onClick={() => {
                          clearPromptErrorAt(index)
                          setPromptDrafts((rows) =>
                            rows.filter((_, rowIndex) => rowIndex !== index),
                          )
                        }}
                      >
                        Remove
                      </Button>
                    ) : null}
                  </div>
                  <label className="block space-y-1">
                    <span className="text-sm font-medium">Question</span>
                    <textarea
                      value={draft.text}
                      disabled={busy || locked}
                      rows={2}
                      aria-invalid={rowError ? true : undefined}
                      aria-describedby={rowError ? rowErrorId : undefined}
                      onChange={(event) =>
                        updatePromptDraft(index, (row) => ({
                          ...row,
                          text: event.target.value,
                        }))
                      }
                      className={customFieldInputClass(Boolean(rowError))}
                    />
                  </label>
                  <label className="block space-y-1">
                    <span className="text-sm font-medium">Category</span>
                    <select
                      value={draft.category}
                      disabled={busy || locked}
                      aria-invalid={rowError ? true : undefined}
                      aria-describedby={rowError ? rowErrorId : undefined}
                      onChange={(event) =>
                        updatePromptDraft(index, (row) => ({
                          ...row,
                          category: event.target.value,
                        }))
                      }
                      className={customFieldInputClass(Boolean(rowError))}
                    >
                      {PROMPT_CATEGORIES.map((category) => (
                        <option key={category} value={category}>
                          {category}
                        </option>
                      ))}
                    </select>
                  </label>
                  {rowError ? (
                    <p
                      id={rowErrorId}
                      role="alert"
                      className="rounded-lg border border-danger-border/60 bg-white/70 px-3 py-2 text-sm text-danger-strong"
                    >
                      {rowError}
                    </p>
                  ) : null}
                </li>
              )
            })}
          </ul>
          <div className="flex flex-wrap gap-3">
            <Button
              type="button"
              variant="secondary"
              disabled={busy || newUserPrompts >= MAX_USER_PROMPTS}
              onClick={() =>
                setPromptDrafts((rows) => [
                  ...rows,
                  { text: '', category: 'custom', source: 'user' },
                ])
              }
            >
              Add custom prompt
            </Button>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button type="button" variant="secondary" disabled={busy} onClick={() => setStep('profile')}>
              Back
            </Button>
            <Button type="button" loading={busy} onClick={() => savePrompts(true)}>
              Save and continue
            </Button>
          </div>
        </section>
      ) : null}

      {step === 'measure' ? (
        <section className="space-y-6 rounded-2xl border border-surface-border bg-surface p-6">
          <h2 className="text-lg font-semibold">Ready to measure</h2>
          <p className="text-sm text-surface-subtle">
            We will ask {promptDrafts.length} prompts across the AI engine panel,
            measure footprints, and compute your GEO score. This step uses your
            analysis quota slot but does not charge the monthly flow again.
          </p>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-surface-subtle">Company</dt>
              <dd className="font-medium">{kycDraft.company || '—'}</dd>
            </div>
            <div>
              <dt className="text-surface-subtle">Category</dt>
              <dd className="font-medium">{kycDraft.category || '—'}</dd>
            </div>
            <div>
              <dt className="text-surface-subtle">Prompts</dt>
              <dd className="font-medium">{promptDrafts.length}</dd>
            </div>
          </dl>
          <div className="flex flex-wrap gap-3">
            <Button type="button" variant="secondary" disabled={busy} onClick={() => setStep('prompts')}>
              Back
            </Button>
            <Button type="button" loading={busy} onClick={runMeasure}>
              Run measurement
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  )
}
