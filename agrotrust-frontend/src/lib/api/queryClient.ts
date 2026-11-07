import { QueryClient } from "@tanstack/react-query";
import { isRetryable } from "./errors";

// Money-touching mutations (fund an order, release escrow, repay a loan)
// must never retry automatically: a network blip after the server already
// applied the change would double-submit. Idempotency-Key headers on the
// backend make a true retry safe, but "safe" is not the same as "correct
// default," so retries stay off globally and callers opt in per-call only
// when they have a reason to.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => failureCount < 2 && isRetryable(error),
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
});
