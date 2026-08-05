import RequireAuth from '@/components/RequireAuth'

/** Signed-in product surface — see RequireAuth for why the guard is client-side. */
export default function Layout({ children }: { children: React.ReactNode }) {
  return <RequireAuth>{children}</RequireAuth>
}
