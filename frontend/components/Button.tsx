import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

// The focus ring lives here rather than in the shared classes below because
// `danger` needs its own: a teal ring around a red destructive button reads as
// a rendering bug. Every other variant keeps the primary ring it always had.
const VARIANT_CLASSES: Record<Variant, string> = {
  primary: 'bg-primary text-white hover:bg-primary-hover focus-visible:ring-primary',
  secondary:
    'bg-white border border-surface-border text-surface-foreground hover:bg-surface-muted focus-visible:ring-primary',
  ghost: 'bg-transparent text-primary hover:bg-primary-soft focus-visible:ring-primary',
  // Reserved for irreversible actions — deleting, removing, revoking. Using it
  // for an ordinary submit spends the one signal the user has for "this one is
  // different".
  danger: 'bg-danger text-white hover:bg-danger-strong focus-visible:ring-danger',
}

// Heights keep interactive targets at least 40px tall (accessibility baseline §7).
const SIZE_CLASSES: Record<Size, string> = {
  sm: 'h-10 px-3 text-sm',
  md: 'h-11 px-5 text-base',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
}

export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  className = '',
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={[
        'inline-flex items-center justify-center gap-2 rounded-md font-medium',
        'transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
        'disabled:cursor-not-allowed disabled:opacity-50',
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        className,
      ].join(' ')}
      {...rest}
    >
      {loading ? <Spinner /> : null}
      {children}
    </button>
  )
}

function Spinner() {
  return (
    <svg
      className="h-4 w-4 motion-safe:animate-spin"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z"
      />
    </svg>
  )
}
