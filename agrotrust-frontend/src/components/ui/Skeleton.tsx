import { cn } from "@/lib/utilities/cn";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded bg-border/60", className)} />;
}
