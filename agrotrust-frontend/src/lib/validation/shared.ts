import { z } from "zod";

// A decimal-as-string validator with a custom .refine(), not
// z.coerce.number(), because coercion creates an input/output type
// mismatch that zodResolver's generics choke on (string in, number out
// breaks form typing), and because the backend wants Decimal-safe strings
// anyway, not floats.
export function numberInRange({ min, max, message }: { min: number; max?: number; message: string }) {
  return z.string().refine(
    (val) => {
      const n = Number(val);
      if (Number.isNaN(n)) return false;
      if (n < min) return false;
      if (max !== undefined && n > max) return false;
      return true;
    },
    { message },
  );
}
