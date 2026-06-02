import { useEffect, useCallback, useRef } from 'react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  confirming?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Delete',
  danger = true,
  confirming = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  // Focus the cancel button when the dialog opens, restore focus on close
  useEffect(() => {
    if (open) {
      previousFocusRef.current = document.activeElement as HTMLElement;
      document.body.style.overflow = 'hidden';
      const id = requestAnimationFrame(() => {
        cancelButtonRef.current?.focus();
      });
      return () => {
        cancelAnimationFrame(id);
        document.body.style.overflow = '';
        previousFocusRef.current?.focus();
      };
    }
  }, [open]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel();
        return;
      }

      // Focus trap: keep Tab cycling within the dialog
      if (e.key === 'Tab' && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    },
    [onCancel]
  );

  useEffect(() => {
    if (open) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div className="modal-overlay" role="button" tabIndex={0} onClick={onCancel} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onCancel() }}>
      <dialog
        ref={dialogRef}
        className="modal-card"
        open
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-message"
        onClick={(e) => e.stopPropagation()}
      >
        <div id="confirm-dialog-title" className="modal-title">{title}</div>
        <div id="confirm-dialog-message" className="modal-message">{message}</div>
        <div className="modal-actions">
          <button
            ref={cancelButtonRef}
            className="btn btn-secondary"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            className={danger ? 'btn btn-danger' : 'btn btn-primary'}
            onClick={onConfirm}
            disabled={confirming}
          >
            {confirming ? 'Deleting...' : confirmLabel}
          </button>
        </div>
      </dialog>
    </div>
  );
}
