'use client'

import { useId, type ReactNode } from 'react'
import Button from '@/components/Button'
import ModalDialog from '@/components/ModalDialog'

/**
 * "Are you sure?" as a real dialog rather than `window.confirm`.
 *
 * The native one was doing the job in the sense that it stopped an accidental
 * click, but it is the browser's chrome, not the product's: it cannot show the
 * failure that follows, it renders unstyled in a rewritten voice ("localhost:8140
 * says"), and it blocks the whole thread while it is up. This is the same
 * question asked inside the app.
 *
 * Two decisions worth naming, both about not making destruction easy:
 *
 * * **Cancel takes focus, not Confirm.** A dialog that opens with the
 *   destructive button focused turns a stray Enter into a deletion. The safe
 *   action is the one under the fingers.
 * * **It stays open while the request runs, and shows the failure in place.**
 *   Closing optimistically would leave a refusal with nowhere to appear, and
 *   the caller would have to invent a second surface for it.
 */
export default function ConfirmDialog({
  title,
  description,
  confirmLabel,
  pendingLabel,
  cancelLabel = 'Cancel',
  tone = 'danger',
  pending = false,
  error = null,
  onConfirm,
  onCancel,
}: {
  title: string
  /** The consequence, in the user's terms. Nodes so a caller can emphasise. */
  description: ReactNode
  confirmLabel: string
  /** Shown on the confirm button while the request is in flight. */
  pendingLabel?: string
  cancelLabel?: string
  tone?: 'danger' | 'primary'
  pending?: boolean
  /** A refusal from the server, rendered inside the dialog. */
  error?: string | null
  onConfirm: () => void
  onCancel: () => void
}) {
  const titleId = useId()
  const descriptionId = useId()
  const cancelId = useId()

  return (
    <ModalDialog
      labelledBy={titleId}
      describedBy={descriptionId}
      onDismiss={onCancel}
      dismissible={!pending}
      initialFocusId={cancelId}
      panelClassName="w-full sm:max-w-md"
    >
      <div className="px-6 py-5 sm:px-7 sm:py-6">
        <h2
          id={titleId}
          className="text-xl font-semibold tracking-tight text-surface-foreground"
        >
          {title}
        </h2>
        <div
          id={descriptionId}
          className="mt-2 space-y-2 text-sm leading-relaxed text-surface-subtle"
        >
          {description}
        </div>

        {error ? (
          <p
            role="alert"
            className="mt-4 rounded-lg bg-danger-soft p-3 text-sm text-danger-strong"
          >
            {error}
          </p>
        ) : null}
      </div>

      <footer className="flex flex-col-reverse gap-3 border-t border-surface-border px-6 py-4 sm:flex-row sm:justify-end sm:px-7">
        <Button
          id={cancelId}
          type="button"
          variant="secondary"
          onClick={onCancel}
          disabled={pending}
        >
          {cancelLabel}
        </Button>
        <Button
          type="button"
          variant={tone === 'danger' ? 'danger' : 'primary'}
          onClick={onConfirm}
          loading={pending}
        >
          {pending && pendingLabel ? pendingLabel : confirmLabel}
        </Button>
      </footer>
    </ModalDialog>
  )
}
