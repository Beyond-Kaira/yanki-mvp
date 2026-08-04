// Reader-facing copy for the pipeline steps, shared by the progress trail and
// the failure card so both always describe a step the same way.
//
// The copy has to hold for BOTH flows that render it: an MVP analysis crawls the
// submitted URL, while a checker run seeds discovery from the submitted brand +
// category and makes no HTTP request at all (the `is_checker` branch in
// backend/app/pipeline/runner.py). Discovery therefore cannot claim to be
// reading a website — a checker run has no website to read.

import type { PipelineStep } from './contracts'

// Present-continuous phrase describing what a step is doing. Shown live for the
// active step, and reused by the failure card ("It stopped while …").
export const STEP_PHRASES: Record<PipelineStep, string> = {
  discovery: 'gathering your company details',
  kyc: 'building your company profile',
  prompts: 'writing the questions your buyers ask',
  execute: 'asking the AI engines about you',
  footprint: 'checking where you show up',
  scoring: 'scoring your visibility',
}

// One-line explanation of the ACTIVE step, shown under its label so the trail
// reads as narration rather than jargon.
export const STEP_DESCRIPTIONS: Record<PipelineStep, string> = {
  discovery: 'Collecting the details we start from.',
  kyc: 'Turning them into a company profile.',
  prompts: 'Generating the questions your buyers ask.',
  execute: 'Running your buyer questions against each engine.',
  footprint: 'Scanning every answer for your brand.',
  scoring: 'Calculating your GEO score.',
}
