'use client'

import Link from 'next/link'
import SessionsSection from '@/components/settings/SessionsSection'
import PageContainer from '@/components/shell/PageContainer'
import { useAuth } from '@/components/AuthProvider'

const ROLE_LABELS: Record<string, string> = {
  owner: 'Owner',
  admin: 'Admin',
  billing_admin: 'Billing admin',
  manager: 'Manager',
  editor: 'Editor',
  analyst: 'Analyst',
  viewer: 'Viewer',
  guest: 'Guest (client)',
}

/**
 * Profile: the real account, from `/auth/me`.
 *
 * It replaces a static page that showed placeholder text — which is worse than
 * showing nothing, because a settings screen that invents values teaches people
 * not to trust the ones that are real.
 */
export default function SettingsPage() {
  const { user } = useAuth()

  return (
    <PageContainer>
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
        Profile
      </h1>
      <p className="mt-1 text-sm text-surface-subtle">
        Your account and the organization you are working in.
      </p>

      {!user ? (
        <p className="mt-8 text-sm text-surface-subtle" role="status">
          Loading your account…
        </p>
      ) : (
        <div className="mt-8 space-y-6">
          <section className="rounded-lg border border-surface-border bg-surface p-5">
            <h2 className="text-base font-semibold">Account</h2>
            <dl className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2">
              <div>
                <dt className="text-xs uppercase tracking-wide text-surface-subtle">
                  Email
                </dt>
                <dd className="mt-0.5 break-all text-sm">{user.email}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-surface-subtle">
                  Status
                </dt>
                <dd className="mt-0.5 text-sm">
                  {user.status === 'disabled' ? 'Disabled' : 'Active'}
                </dd>
              </div>
            </dl>
          </section>

          <section className="rounded-lg border border-surface-border bg-surface p-5">
            <h2 className="text-base font-semibold">Organization</h2>
            {user.organization ? (
              <>
                <dl className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2">
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-surface-subtle">
                      Name
                    </dt>
                    <dd className="mt-0.5 text-sm">{user.organization.name}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-surface-subtle">
                      Type
                    </dt>
                    <dd className="mt-0.5 text-sm">
                      {user.organization.kind === 'company'
                        ? 'Organization'
                        : 'Individual'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-surface-subtle">
                      Your role
                    </dt>
                    <dd className="mt-0.5 text-sm">
                      {user.role ? (ROLE_LABELS[user.role] ?? user.role) : '—'}
                    </dd>
                  </div>
                </dl>
                <Link
                  href="/admin"
                  className="mt-4 inline-flex min-h-[44px] items-center rounded-md border border-surface-border px-4 text-sm font-medium transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  Open the Admin Panel
                </Link>
              </>
            ) : (
              <p className="mt-2 text-sm text-surface-subtle">
                You are not in an organization yet.
              </p>
            )}
          </section>

          <SessionsSection />
        </div>
      )}
    </PageContainer>
  )
}
