import { forwardRef, type SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utilities/cn";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, label, error, id, children, ...props }, ref) => {
    const selectId = id ?? props.name;
    return (
      <div className="flex flex-col gap-1">
        {label && (
          <label htmlFor={selectId} className="text-sm font-medium text-foreground">
            {label}
          </label>
        )}
        <select
          ref={ref}
          id={selectId}
          className={cn(
            "h-10 rounded border border-border bg-surface px-3 text-sm text-foreground",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
            error && "border-danger",
            className,
          )}
          {...props}
        >
          {children}
        </select>
        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    );
  },
);
Select.displayName = "Select";
