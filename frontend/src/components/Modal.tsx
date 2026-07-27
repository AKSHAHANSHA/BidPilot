import { useEffect, useRef, type ReactNode } from "react";
import { Button } from "./ui";

/**
 * An accessible modal: focus is moved in on open, Escape closes, a backdrop click closes, and
 * focus is restricted to the dialog while open. Used for forms and confirmations.
 */
export function Modal({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-auto p-4"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-ink/40" />
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`relative bg-surface border-2 border-rule rounded-[3px] my-8 w-full ${
          wide ? "max-w-3xl" : "max-w-lg"
        } outline-none`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-rule px-5 py-3">
          <h2 className="font-display text-xl">{title}</h2>
          <Button variant="ghost" onClick={onClose} aria-label="Close">
            ✕
          </Button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Delete",
  onConfirm,
  onClose,
  busy = false,
}: {
  title: string;
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onClose: () => void;
  busy?: boolean;
}) {
  return (
    <Modal title={title} onClose={onClose}>
      <p className="text-sm text-ink mb-6">{message}</p>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button variant="danger" onClick={onConfirm} disabled={busy}>
          {busy ? "Working…" : confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
