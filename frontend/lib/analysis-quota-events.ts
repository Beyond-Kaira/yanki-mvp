type QuotaListener = () => void

const listeners = new Set<QuotaListener>()

export function subscribeAnalysisQuotaChanged(listener: QuotaListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function notifyAnalysisQuotaChanged(): void {
  listeners.forEach((listener) => listener())
}
