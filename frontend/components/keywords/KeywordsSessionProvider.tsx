'use client'

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type {
  KeywordExpandResponse,
  KeywordOverviewResponse,
  KeywordRankHit,
} from '@/lib/contracts'

type RankByQuery = Record<string, KeywordRankHit>

type KeywordsSessionValue = {
  overviewQuery: string
  setOverviewQuery: (value: string) => void
  magicQuery: string
  setMagicQuery: (value: string) => void
  locale: string
  setLocale: (value: string) => void
  domain: string
  setDomain: (value: string) => void

  overviewLoading: boolean
  setOverviewLoading: (value: boolean) => void
  overviewError: string | null
  setOverviewError: (value: string | null) => void
  overviewResult: KeywordOverviewResponse | null
  setOverviewResult: (value: KeywordOverviewResponse | null) => void

  magicLoading: boolean
  setMagicLoading: (value: boolean) => void
  rankLoading: boolean
  setRankLoading: (value: boolean) => void
  magicError: string | null
  setMagicError: (value: string | null) => void
  magicResult: KeywordExpandResponse | null
  setMagicResult: (value: KeywordExpandResponse | null) => void
  selected: Set<string>
  setSelected: (value: Set<string>) => void
  togglePhrase: (phrase: string) => void
  toggleAllPhrases: (phrases: string[]) => void
  ranks: RankByQuery
  setRanks: (value: RankByQuery) => void
  mergeRanks: (value: RankByQuery) => void
  clearMagicSelection: () => void
}

const KeywordsSessionContext = createContext<KeywordsSessionValue | null>(null)

export function useKeywordsSession(): KeywordsSessionValue {
  const value = useContext(KeywordsSessionContext)
  if (!value) {
    throw new Error('useKeywordsSession must be used within KeywordsSessionProvider')
  }
  return value
}

export default function KeywordsSessionProvider({
  children,
}: {
  children: ReactNode
}) {
  const [overviewQuery, setOverviewQuery] = useState('')
  const [magicQuery, setMagicQuery] = useState('')
  // ISO-3166 country code, matching the locale picker's values.
  const [locale, setLocale] = useState('us')
  const [domain, setDomain] = useState('')

  const [overviewLoading, setOverviewLoading] = useState(false)
  const [overviewError, setOverviewError] = useState<string | null>(null)
  const [overviewResult, setOverviewResult] =
    useState<KeywordOverviewResponse | null>(null)

  const [magicLoading, setMagicLoading] = useState(false)
  const [rankLoading, setRankLoading] = useState(false)
  const [magicError, setMagicError] = useState<string | null>(null)
  const [magicResult, setMagicResult] = useState<KeywordExpandResponse | null>(
    null,
  )
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [ranks, setRanks] = useState<RankByQuery>({})

  const togglePhrase = useCallback((phrase: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(phrase)) next.delete(phrase)
      else next.add(phrase)
      return next
    })
  }, [])

  const toggleAllPhrases = useCallback((phrases: string[]) => {
    setSelected((prev) => {
      if (phrases.length > 0 && prev.size === phrases.length) return new Set()
      return new Set(phrases)
    })
  }, [])

  const mergeRanks = useCallback((value: RankByQuery) => {
    setRanks((prev) => ({ ...prev, ...value }))
  }, [])

  const clearMagicSelection = useCallback(() => {
    setSelected(new Set())
    setRanks({})
  }, [])

  const value = useMemo<KeywordsSessionValue>(
    () => ({
      overviewQuery,
      setOverviewQuery,
      magicQuery,
      setMagicQuery,
      locale,
      setLocale,
      domain,
      setDomain,
      overviewLoading,
      setOverviewLoading,
      overviewError,
      setOverviewError,
      overviewResult,
      setOverviewResult,
      magicLoading,
      setMagicLoading,
      rankLoading,
      setRankLoading,
      magicError,
      setMagicError,
      magicResult,
      setMagicResult,
      selected,
      setSelected,
      togglePhrase,
      toggleAllPhrases,
      ranks,
      setRanks,
      mergeRanks,
      clearMagicSelection,
    }),
    [
      overviewQuery,
      magicQuery,
      locale,
      domain,
      overviewLoading,
      overviewError,
      overviewResult,
      magicLoading,
      rankLoading,
      magicError,
      magicResult,
      selected,
      ranks,
      togglePhrase,
      toggleAllPhrases,
      mergeRanks,
      clearMagicSelection,
    ],
  )

  return (
    <KeywordsSessionContext.Provider value={value}>
      {children}
    </KeywordsSessionContext.Provider>
  )
}
