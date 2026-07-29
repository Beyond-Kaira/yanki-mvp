'use client'

import { useState } from 'react'
import type { InputHTMLAttributes } from 'react'
import { FieldShell, fieldDescribedBy, fieldInputClass } from './FormField'

interface PasswordFieldProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id' | 'type'> {
  id: string
  label: string
  error?: string | null
  hint?: string
}

// A password input with a reveal toggle. The toggle is a real button so it is
// reachable by keyboard and announced with its state; it never becomes the
// field's only affordance, and hiding is always the starting point.
export default function PasswordField({
  id,
  label,
  error,
  hint,
  disabled,
  ...rest
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false)
  const invalid = Boolean(error)

  return (
    <FieldShell id={id} label={label} error={error} hint={hint}>
      <div className="relative">
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          disabled={disabled}
          aria-invalid={invalid || undefined}
          aria-describedby={fieldDescribedBy(id, error, hint)}
          // Room on the right so a long value never runs under the toggle.
          className={`${fieldInputClass(invalid)} pr-12`}
          {...rest}
        />
        <button
          type="button"
          onClick={() => setVisible((current) => !current)}
          disabled={disabled}
          aria-pressed={visible}
          aria-controls={id}
          className="absolute inset-y-0 right-0 inline-flex min-h-[40px] items-center rounded-r-lg px-3 text-sm font-medium text-surface-subtle hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50"
        >
          {visible ? 'Hide' : 'Show'}
          <span className="sr-only"> password</span>
        </button>
      </div>
    </FieldShell>
  )
}
