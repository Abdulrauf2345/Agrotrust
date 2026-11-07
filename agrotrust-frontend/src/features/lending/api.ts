import { apiRequest } from "@/lib/api/client";
import type { CreditAssessment, Loan, LoanApplication, LoanProduct, RepaymentInstallment } from "@/types/api";

export interface CreateLoanProductPayload {
  lender_org_id: string;
  name: string;
  min_amount_minor: number;
  max_amount_minor: number;
  min_term_months: number;
  max_term_months: number;
  annual_rate_bps: number;
  late_fee_bps?: number;
  min_credit_score?: number;
  requires_verified_farm?: boolean;
}

export function createLoanProduct(payload: CreateLoanProductPayload): Promise<LoanProduct> {
  return apiRequest<LoanProduct>("/api/v1/loan-products", { method: "POST", body: payload });
}

export function listLoanProducts(lenderOrgId?: string): Promise<LoanProduct[]> {
  return apiRequest<LoanProduct[]>("/api/v1/loan-products", { query: { lender_org_id: lenderOrgId } });
}

export interface ApplyForLoanPayload {
  product_id: string;
  amount_minor: number;
  term_months: number;
  purpose?: string;
}

export function applyForLoan(payload: ApplyForLoanPayload): Promise<LoanApplication> {
  return apiRequest<LoanApplication>("/api/v1/loan-applications", { method: "POST", body: payload });
}

export function listLoanApplications(): Promise<LoanApplication[]> {
  return apiRequest<LoanApplication[]>("/api/v1/loan-applications");
}

export interface DecideLoanApplicationPayload {
  approve: boolean;
  reason?: string;
  override?: boolean;
}

export function decideLoanApplication(id: string, payload: DecideLoanApplicationPayload): Promise<LoanApplication> {
  return apiRequest<LoanApplication>(`/api/v1/loan-applications/${id}/decide`, { method: "POST", body: payload });
}

export function disburseLoan(applicationId: string, idempotencyKey: string): Promise<Loan> {
  return apiRequest<Loan>(`/api/v1/loan-applications/${applicationId}/disburse`, {
    method: "POST",
    idempotencyKey,
  });
}

export function listLoans(): Promise<Loan[]> {
  return apiRequest<Loan[]>("/api/v1/loans");
}

export function getLoan(id: string): Promise<Loan> {
  return apiRequest<Loan>(`/api/v1/loans/${id}`);
}

export function getLoanSchedule(id: string): Promise<RepaymentInstallment[]> {
  return apiRequest<RepaymentInstallment[]>(`/api/v1/loans/${id}/schedule`);
}

export function repayLoan(id: string, amountMinor: number, idempotencyKey: string): Promise<Loan> {
  return apiRequest<Loan>(`/api/v1/loans/${id}/repay`, {
    method: "POST",
    body: { amount_minor: amountMinor },
    idempotencyKey,
  });
}

export function myCredit(): Promise<CreditAssessment> {
  return apiRequest<CreditAssessment>("/api/v1/credit/me");
}
