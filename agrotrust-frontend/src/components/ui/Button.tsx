import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utilities/cn";
import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-primary text-primary-foreground hover:opacity-90",
  secondary: "bg-surface border border-border text-foreground hover:bg-background",
  ghost: "text-foreground hover:bg-surface",
  danger: "bg-danger text-white hover:opacity-90",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-base",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", loading, disabled, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded font-medium transition-colors",
          "disabled:opacity-50 disabled:pointer-events-none",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2",
          VARIANT_CLASSES[variant],
          SIZE_CLASSES[size],
          className,
        )}
        disabled={disabled || loading}
        {...props}
      >
        {loading && <Spinner size={16} />}
        {children}
      </button>
    );
  },
);
Button.displayName = "Button";
