import { Check } from "lucide-react";
import { cn } from "@/lib/utilities/cn";
import type { OrderState } from "@/types/api";

// The happy-path sequence. DELIVERY_FAILED, DISPUTED and CANCELLED are
// terminal/side branches shown separately rather than inline in this
// linear strip, since they don't have a fixed position in the sequence.
const HAPPY_PATH: OrderState[] = [
  "CREATED",
  "CONFIRMED",
  "FUNDED",
  "PREPARING",
  "IN_TRANSIT",
  "DELIVERED",
  "INSPECTED",
  "COMPLETED",
];

const LABELS: Record<OrderState, string> = {
  CREATED: "Created",
  CONFIRMED: "Confirmed",
  FUNDED: "Funded",
  PREPARING: "Preparing",
  IN_TRANSIT: "In transit",
  DELIVERED: "Delivered",
  DELIVERY_FAILED: "Delivery failed",
  INSPECTED: "Inspected",
  DISPUTED: "Disputed",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
};

export function OrderTimeline({ state }: { state: OrderState }) {
  if (state === "CANCELLED" || state === "DISPUTED" || state === "DELIVERY_FAILED") {
    return (
      <div className="rounded border border-danger/30 bg-danger/5 p-3 text-sm font-medium text-danger">
        {LABELS[state]}
      </div>
    );
  }

  const currentIndex = HAPPY_PATH.indexOf(state);

  return (
    <ol className="flex flex-wrap items-center gap-1">
      {HAPPY_PATH.map((step, i) => {
        const done = i < currentIndex;
        const active = i === currentIndex;
        return (
          <li key={step} className="flex items-center gap-1">
            <div
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-full border text-xs font-medium",
                done && "border-primary bg-primary text-primary-foreground",
                active && "border-primary text-primary",
                !done && !active && "border-border text-muted",
              )}
            >
              {done ? <Check size={14} /> : i + 1}
            </div>
            <span className={cn("text-xs", active ? "font-medium text-foreground" : "text-muted")}>
              {LABELS[step]}
            </span>
            {i < HAPPY_PATH.length - 1 && <div className="mx-1 h-px w-4 bg-border" />}
          </li>
        );
      })}
    </ol>
  );
}
