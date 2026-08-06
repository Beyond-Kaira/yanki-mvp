'use client'

import { useRouter } from 'next/navigation'
import { useEffect, type ReactNode } from 'react'
import { useAuth } from '@/components/AuthProvider'

interface SignedInGateProps {
  hinted: boolean
  to?: string
  children: ReactNode
}

export default function SignedInGate({
  hinted,
  to = '/dashboard',
  children,
}: SignedInGateProps) {
  const { status } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (status === 'authenticated') router.replace(to)
  }, [status, to, router])

  if (status === 'authenticated') return null
  if (hinted && status === 'loading') return null

  return <>{children}</>
}
