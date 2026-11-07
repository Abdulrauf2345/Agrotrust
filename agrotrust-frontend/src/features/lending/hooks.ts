import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./api";

export function useLoanProducts(lenderOrgId?: string) {
  return useQuery({
    queryKey: ["lending", "products", lenderOrgId ?? null],
    queryFn: () => api.listLoanProducts(lenderOrgId),
  });
}

export function useCreateLoanProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createLoanProduct,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["lending", "products"] });
    },
  });
}

export function useLoanApplications() {
  return useQuery({
    queryKey: ["lending", "applications"],
    queryFn: api.listLoanApplications,
  });
}

export function useApplyForLoan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.applyForLoan,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["lending", "applications"] });
    },
  });
}

export function useDecideLoanApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }: { id: string } & api.DecideLoanApplicationPayload) =>
      api.decideLoanApplication(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["lending", "applications"] });
    },
  });
}

export function useDisburseLoan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (applicationId: string) => api.disburseLoan(applicationId, crypto.randomUUID()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["lending", "applications"] });
      queryClient.invalidateQueries({ queryKey: ["lending", "loans"] });
    },
  });
}

export function useLoans() {
  return useQuery({
    queryKey: ["lending", "loans"],
    queryFn: api.listLoans,
  });
}

export function useLoan(id: string | undefined) {
  return useQuery({
    queryKey: ["lending", "loans", id],
    queryFn: () => api.getLoan(id as string),
    enabled: Boolean(id),
  });
}

export function useLoanSchedule(id: string | undefined) {
  return useQuery({
    queryKey: ["lending", "loans", id, "schedule"],
    queryFn: () => api.getLoanSchedule(id as string),
    enabled: Boolean(id),
  });
}

export function useRepayLoan(loanId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (amountMinor: number) => api.repayLoan(loanId, amountMinor, crypto.randomUUID()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["lending", "loans", loanId] });
      queryClient.invalidateQueries({ queryKey: ["lending", "loans"] });
    },
  });
}

export function useMyCredit() {
  return useQuery({
    queryKey: ["lending", "credit", "me"],
    queryFn: api.myCredit,
    retry: false,
  });
}
