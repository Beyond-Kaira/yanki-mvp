import type { InputHTMLAttributes, ReactNode } from 'react'
import { fieldErrorId } from './FormField'

interface CheckboxProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id' | 'type'> {
  id: string
  // A node rather than a string: the terms checkbox carries links inside its
  // label, and those have to sit inside the clickable label text.
  label: ReactNode
  error?: string | null
}

export default function Checkbox({
  id,
  label,
  error,
  ...rest
}: CheckboxProps) {
  const invalid = Boolean(error)

  return (
    <div className="space-y-1.5">
      <div className="flex items-start gap-2.5">
        <input
          id={id}
          type="checkbox"
          aria-invalid={invalid || undefined}
          aria-describedby={invalid ? fieldErrorId(id) : undefined}
          // mt-0.5 keeps the box aligned with the first line of a wrapping label.
          className={`mt-0.5 h-4 w-4 shrink-0 rounded border bg-white text-primary accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:opacity-50 ${
            invalid ? 'border-danger' : 'border-surface-subtle'
          }`}
          {...rest}
        />
        <label htmlFor={id} className="text-sm text-surface-foreground">
          {label}
        </label>
      </div>
      {error ? (
        <p id={fieldErrorId(id)} className="text-sm text-danger">
          {error}
        </p>
      ) : null}
    </div>
  )
}
