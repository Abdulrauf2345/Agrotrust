import type { HTMLAttributes } from "react";
import { AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { cn } from "@/lib/utilities/cn";

type Tone = "info" | "success" | "danger";

const ICONS = { info: Info, success: CheckCircle2, danger: AlertTriangle };

const TONE_CLASSES: Record<Tone, string> = {
  info: "border-primary/30 bg-primary/5 text-foreground",
  success: "border-success/30 bg-success/5 text-foreground",
  danger: "border-danger/30 bg-danger/5 text-foreground",
};

export function Alert({
  className,
  tone = "info",
  children,
  ...props
}: HTMLAttributes<HTMLDivElement> & { tone?: Tone }) {
  const Icon = ICONS[tone];
  return (
    <div
      role="alert"
      className={cn("flex items-start gap-2 rounded border p-3 text-sm", TONE_CLASSES[tone], className)}
      {...props}
    >
      <Icon size={18} className="mt-0.5 shrink-0" />
      <div>{children}</div>
    </div>
  );
}
