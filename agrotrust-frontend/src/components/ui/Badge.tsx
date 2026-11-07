import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utilities/cn";

type Tone = "neutral" | "success" | "warning" | "danger" | "primary";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-background text-muted border-border",
  success: "bg-success/10 text-success border-success/30",
  warning: "bg-warning/10 text-warning border-warning/30",
  danger: "bg-danger/10 text-danger border-danger/30",
  primary: "bg-primary/10 text-primary border-primary/30",
};

export function Badge({
  className,
  tone = "neutral",
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
        TONE_CLASSES[tone],
        className,
      )}
      {...props}
    />
  );
}
