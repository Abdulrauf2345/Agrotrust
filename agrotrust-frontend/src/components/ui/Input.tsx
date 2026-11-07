import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utilities/cn";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, id, ...props }, ref) => {
    const inputId = id ?? props.name;
    return (
      <div className="flex flex-col gap-1">
        {label && (
          <label htmlFor={inputId} className="text-sm font-medium text-foreground">
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            "h-10 rounded border border-border bg-surface px-3 text-sm text-foreground",
            "placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
            error && "border-danger focus-visible:ring-danger",
            className,
          )}
          aria-invalid={!!error}
          aria-describedby={error ? `${inputId}-error` : undefined}
          {...props}
        />
        {error && (
          <p id={`${inputId}-error`} className="text-sm text-danger">
            {error}
          </p>
        )}
      </div>
    );
  },
);
Input.displayName = "Input";
