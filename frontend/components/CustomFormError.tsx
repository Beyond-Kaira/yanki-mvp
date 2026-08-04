import type { ReactNode } from 'react'

interface CustomFormErrorProps {
  id: string
  children: ReactNode
}

// Form-level failure: the request was made and came back rejected, so this is
// about the submission rather than one field. `role="alert"` announces it on
// every entry, including a repeat submit that fails the same way.
export default function CustomFormError({ id, children }: CustomFormErrorProps) {
  return (
    <p
      id={id}
      role="alert"
      className="rounded-lg border border-danger bg-danger-soft px-4 py-3 text-sm text-surface-foreground"
    >
      {children}
    </p>
  )
}
