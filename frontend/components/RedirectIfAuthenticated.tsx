'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { useAuth } from '@/components/AuthProvider'

export default function RedirectIfAuthenticated({ to = '/dashboard' }: { to?: string }) {
  const { status } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (status === 'authenticated') router.replace(to)
  }, [status, to, router])

  return null
}
