// Reader-facing copy for the pipeline steps, shared by the progress trail and
// the failure card so both always describe a step the same way.
//
// The copy has to hold for BOTH flows that render it: an MVP analysis crawls the
// submitted URL, while a checker run seeds discovery from the submitted brand +
// category and makes no HTTP request at all (the `is_checker` branch in
// backend/app/pipeline/runner.py). Discovery therefore cannot claim to be
// reading a website — a checker run has no website to read.

import type { AnalysisStatus, PipelineStep } from './contracts'

export type StepState = 'done' | 'active' | 'failed' | 'pending'

export const ANALYSIS_STEPS: { key: PipelineStep; label: string; threshold: number }[] = [
  { key: 'discovery', label: 'Discovery', threshold: 15 },
  { key: 'kyc', label: 'KYC', threshold: 30 },
  { key: 'prompts', label: 'Prompts', threshold: 45 },
  { key: 'execute', label: 'Executing', threshold: 80 },
  { key: 'footprint', label: 'Footprint', threshold: 90 },
  { key: 'scoring', label: 'Scoring', threshold: 100 },
]

export const STEP_STATE_WORD: Record<StepState, string> = {
  done: 'completed', active: 'in progress', failed: 'failed', pending: 'waiting',
}

export function analysisStepState(
  index: number,
  status: AnalysisStatus,
  progress: number,
  currentStep: PipelineStep | null,
): StepState {
  const claimedIndex = ANALYSIS_STEPS.findIndex((step) => step.key === currentStep)
  // Reclaimed jobs can restart without resetting progress. The claimed step
  // takes precedence so neither it nor later steps falsely appear completed.
  if ((status === 'running' || status === 'failed') && claimedIndex >= 0) {
    if (index === claimedIndex) return status === 'failed' ? 'failed' : 'active'
    if (index > claimedIndex) return 'pending'
  }
  if (status === 'done' || progress >= ANALYSIS_STEPS[index].threshold) return 'done'
  if (status === 'running' && currentStep === null &&
      index === ANALYSIS_STEPS.findIndex((step) => progress < step.threshold)) return 'active'
  return 'pending'
}

// Present-continuous phrase describing what a step is doing. Shown live for the
// active step, and reused by the failure card ("It stopped while …").
export const STEP_PHRASES: Record<PipelineStep, string> = {
  discovery: 'gathering your company details',
  kyc: 'building your company profile',
  prompts: 'writing the questions your buyers ask',
  execute: 'auditing your buyer questions across our models',
  footprint: 'checking where you show up',
  scoring: 'scoring your visibility',
}

// One-line explanation of the ACTIVE step, shown under its label so the trail
// reads as narration rather than jargon.
export const STEP_DESCRIPTIONS: Record<PipelineStep, string> = {
  discovery: 'Collecting the details we start from.',
  kyc: 'Turning them into a company profile.',
  prompts: 'Generating the questions your buyers ask.',
  execute: 'Running your buyer questions across each configured model via OpenRouter.',
  footprint: 'Scanning every answer for your brand.',
  scoring: 'Calculating your GEO score.',
}
