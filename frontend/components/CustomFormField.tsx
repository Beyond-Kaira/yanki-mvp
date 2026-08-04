import type { InputHTMLAttributes, ReactNode } from 'react'

// The input chrome, plus the error state the auth screens need.
//
// Scope, stated plainly: four existing forms inline this styling in two
// shapes — UrlForm and CheckerForm match what is below, while WaitlistForm and
// EmailGate use the inline-with-button variant (`min-h-[40px] py-2.5 sm:flex-1`).
// This function covers the first shape only, so it is one definition for the
// auth screens rather than one definition for the app. Folding the other four
// in means giving this a variant argument, which is a change to working forms
// and belongs in its own pass.
export function customFieldInputClass(hasError: boolean): string {
  return [
    'w-full rounded-lg border bg-white px-4 py-3 text-base text-surface-foreground',
    'placeholder:text-surface-subtle focus-visible:outline-none focus-visible:ring-2',
    'disabled:opacity-50',
    hasError
      ? 'border-danger focus-visible:ring-danger'
      : 'border-surface-subtle focus-visible:ring-primary',
  ].join(' ')
}

// The message ids a field publishes, so the control can point at whichever is
// showing with aria-describedby and a screen reader reads it with the field.
export function customFieldErrorId(id: string): string {
  return `${id}-error`
}

export function customFieldHintId(id: string): string {
  return `${id}-hint`
}

// What the control should be described by: the error while there is one, the
// hint otherwise. Never both, so the reason a field is rejected is not buried
// behind a rule the reader has already broken.
export function customFieldDescribedBy(
  id: string,
  error?: string | null,
  hint?: string,
): string | undefined {
  if (error) return customFieldErrorId(id)
  if (hint) return customFieldHintId(id)
  return undefined
}

interface CustomFieldShellProps {
  id: string
  label: string
  error?: string | null
  hint?: string
  children: ReactNode
}

// Label, control, and the message under it. Shared with CustomPasswordField,
// which needs its own control markup for the reveal toggle.
export function CustomFieldShell({
  id,
  label,
  error,
  hint,
  children,
}: CustomFieldShellProps) {
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={id}
        className="block text-sm font-medium text-surface-foreground"
      >
        {label}
      </label>
      {children}
      {error ? (
        // `role="alert"` for the same reason UrlForm and EmailGate carry it: the
        // message has to announce itself. Moving focus to the field is not
        // enough — the focus call in the submit handler runs before React has
        // committed the error, so the control the reader lands on has neither
        // aria-invalid nor aria-describedby on it yet, and only the label is
        // read. This live region says why.
        <p id={customFieldErrorId(id)} role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={customFieldHintId(id)} className="text-xs text-surface-subtle">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

interface CustomFormFieldProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  id: string
  label: string
  error?: string | null
  hint?: string
}

export default function CustomFormField({
  id,
  label,
  error,
  hint,
  ...rest
}: CustomFormFieldProps) {
  const invalid = Boolean(error)

  return (
    <CustomFieldShell id={id} label={label} error={error} hint={hint}>
      <input
        id={id}
        aria-invalid={invalid || undefined}
        aria-describedby={customFieldDescribedBy(id, error, hint)}
        className={customFieldInputClass(invalid)}
        {...rest}
      />
    </CustomFieldShell>
  )
}
