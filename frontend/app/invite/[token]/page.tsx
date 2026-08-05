'use client'

import { use } from 'react'
import InviteClient from './InviteClient'

/**
 * `/invite/<token>` — the public half of the invitation flow.
 *
 * Deliberately outside the product shell and outside `RequireAuth`: the person
 * opening it usually has no account yet, and a redirect to /login would send
 * them to a form they cannot complete.
 *
 * The token is carried in the path rather than a query string so it does not
 * end up in a `Referer` header when the accept page links onward.
 */
export default function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params)
  return <InviteClient token={token} />
}
