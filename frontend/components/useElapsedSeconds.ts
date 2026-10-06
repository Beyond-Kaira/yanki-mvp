'use client'

import { useEffect, useState } from 'react'

/** Count from the run's creation, including time before this view was opened. */
export function useElapsedSeconds(startedAt: string | null, enabled: boolean): number {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    if (!enabled) return
    const parsed = startedAt ? Date.parse(startedAt) : Number.NaN
    const base = Number.isNaN(parsed) ? Date.now() : parsed
    function tick() {
      setSeconds(Math.max(0, Math.floor((Date.now() - base) / 1000)))
    }
    tick()
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [startedAt, enabled])
  return seconds
}

export function formatElapsed(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}
