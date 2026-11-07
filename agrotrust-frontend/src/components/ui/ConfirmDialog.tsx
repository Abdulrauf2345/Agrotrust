import { useState } from "react";
import { Button } from "./Button";
import { Alert } from "./Alert";

// Modeled as a plain inline confirm panel rather than a portal/overlay
// dialog, to keep this scope dependency-light (no Radix Dialog wiring yet).
// A failed onConfirm must not silently close the panel, or the caller loses
// their place and the error vanishes with it - so it stays open and shows
// the error until the user tries again or cancels.
export function ConfirmDialog({
  title,
  onConfirm,
  onCancel,
  confirmLabel = "Confirm",
}: {
  title: string;
  onConfirm: () => Promise<unknown>;
  onCancel: () => void;
  confirmLabel?: string;
}) {
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleConfirm = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 rounded border border-border bg-surface p-4">
      <p className="font-medium text-foreground">{title}</p>
      {error && <Alert tone="danger">{error}</Alert>}
      <div className="flex gap-2">
        <Button size="sm" loading={submitting} onClick={handleConfirm}>
          {confirmLabel}
        </Button>
        <Button size="sm" variant="secondary" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
