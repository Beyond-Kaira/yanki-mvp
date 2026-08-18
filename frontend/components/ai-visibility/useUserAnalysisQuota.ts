'use client'

import { useCallback, useEffect, useState } from 'react'
import { ApiError, listAnalyses } from '@/lib/api'
import { subscribeAnalysisQuotaChanged } from '@/lib/analysis-quota-events'

export type UserAnalysisQuota = {
  used: number
  limit: number
}

export function useUserAnalysisQuota() {
  const [quota, setQuota] = useState<UserAnalysisQuota | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback((signal?: AbortSignal) => {
    setLoading(true)
    setError(null)
    return listAnalyses({ limit: 1 }, signal)
      .then((page) => {
        setQuota({
          used: page.user_analyses_used,
          limit: page.user_analyses_limit,
        })
        setLoading(false)
      })
      .catch((cause: unknown) => {
        if (cause instanceof Error && cause.name === 'AbortError') return
        setError(
          cause instanceof ApiError
            ? cause.message
            : "We couldn't load your analysis quota.",
        )
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    refresh(controller.signal)
    return () => controller.abort()
  }, [refresh])

  useEffect(() => subscribeAnalysisQuotaChanged(() => refresh()), [refresh])

  const atLimit = quota != null && quota.used >= quota.limit

  return { quota, loading, error, atLimit, refresh }
}
