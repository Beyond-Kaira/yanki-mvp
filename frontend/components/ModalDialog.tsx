'use client'

import { useEffect, useRef, type ReactNode } from 'react'

/**
 * The app's one modal shell: backdrop, panel, and the keyboard contract.
 *
 * It exists because a modal is mostly *invisible* work — trapping Tab, closing
 * on Escape, locking the page behind it, and handing focus back where it came
 * from — and every copy of that is a copy that can drift. The crawl-settings
 * dialog owned a private version of it; a second dialog would have made two,
 * so it lives here and both compose it.
 *
 * Deliberately **shell only**. Header, body and footer are the caller's, because
 * the two dialogs that use it do not share a layout: one is a form with an
 * eyebrow and a close button, the other is a short question with two buttons.
 * Pushing that into props would produce a component configured rather than
 * composed, which is how a "reusable" modal ends up with nine boolean flags.
 *
 * The caller supplies `labelledBy` (and optionally `describedBy`) pointing at
 * ids it renders, so the accessible name is the heading the user actually sees
 * rather than a string duplicated in two places.
 */

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'

export default function ModalDialog({
  labelledBy,
  describedBy,
  onDismiss,
  /**
   * False while work is in flight. Escape and backdrop clicks are ignored, so a
   * request that has already left cannot be abandoned by a stray keystroke —
   * the caller disables its own buttons for the same reason.
   */
  dismissible = true,
  /** Element focused on open. Falls back to the first focusable in the panel. */
  initialFocusId,
  panelClassName = 'w-full sm:max-w-lg',
  children,
}: {
  labelledBy: string
  describedBy?: string
  onDismiss: () => void
  dismissible?: boolean
  initialFocusId?: string
  panelClassName?: string
  children: ReactNode
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  // Read through a ref inside the listener so a changing `dismissible` does not
  // tear down and re-add the handler mid-interaction.
  const dismissibleRef = useRef(dismissible)
  dismissibleRef.current = dismissible

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const initial = initialFocusId ? document.getElementById(initialFocusId) : null
    if (initial) {
      initial.focus()
    } else {
      panelRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)?.focus()
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && dismissibleRef.current) {
        onDismiss()
        return
      }
      if (event.key !== 'Tab' || !panelRef.current) return

      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', handleKeyDown)
      previouslyFocused?.focus()
    }
  }, [initialFocusId, onDismiss])

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-ink/60 p-0 backdrop-blur-[2px] sm:items-center sm:p-6"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && dismissibleRef.current) onDismiss()
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        className={`max-h-[calc(100dvh-1rem)] overflow-y-auto rounded-t-2xl bg-surface shadow-2xl sm:max-h-none sm:overflow-visible sm:rounded-2xl ${panelClassName}`}
      >
        {children}
      </div>
    </div>
  )
}
