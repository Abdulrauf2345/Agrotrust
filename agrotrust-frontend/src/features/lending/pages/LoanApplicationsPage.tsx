import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/lib/auth/AuthContext";
import { useDecideLoanApplication, useDisburseLoan, useLoanApplications, useLoans } from "../hooks";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Input } from "@/components/ui/Input";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { LoanApplicationStateBadge, LoanStateBadge } from "@/components/ui/StatusBadge";
import { formatMinor } from "@/lib/formatting/currency";
import { formatDate } from "@/lib/formatting/date";
import { ApiError } from "@/lib/api/errors";
import { paths } from "@/routes/paths";
import type { LoanApplicationState } from "@/types/api";

export function LoanApplicationsPage() {
  const { user } = useAuth();
  const isLender = user?.roles.includes("LENDER") || user?.roles.includes("PLATFORM_ADMIN");
  const { data: applications, isLoading } = useLoanApplications();
  const { data: loans, isLoading: loansLoading } = useLoans();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">My loan applications</h1>

      <Card>
        <CardHeader>
          <CardTitle>Applications</CardTitle>
        </CardHeader>
        {isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : !applications?.length ? (
          <EmptyState title="No applications yet" description="Applications you submit, or that arrive for your loan products, show here." />
        ) : (
          <ul className="flex flex-col gap-3">
            {applications.map((app) => (
              <ApplicationRow key={app.id} applicationId={app.id} state={app.state} amountMinor={app.amount_minor}
                termMonths={app.term_months} createdAt={app.created_at} decisionReason={app.decision_reason}
                canDecide={Boolean(isLender)} />
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Loans</CardTitle>
        </CardHeader>
        {loansLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : !loans?.length ? (
          <EmptyState title="No loans yet" description="Disbursed loans show here with their repayment schedule." />
        ) : (
          <ul className="flex flex-col gap-2">
            {loans.map((loan) => (
              <li key={loan.id} className="flex items-center justify-between rounded border border-border px-3 py-2 text-sm">
                <Link to={paths.loanDetail(loan.id)} className="font-medium text-primary hover:underline">
                  {formatMinor(loan.principal_minor)} &middot; {loan.term_months} months
                </Link>
                <LoanStateBadge state={loan.state} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function ApplicationRow({
  applicationId,
  state,
  amountMinor,
  termMonths,
  createdAt,
  decisionReason,
  canDecide,
}: {
  applicationId: string;
  state: LoanApplicationState;
  amountMinor: number;
  termMonths: number;
  createdAt: string;
  decisionReason: string | null;
  canDecide: boolean;
}) {
  const decide = useDecideLoanApplication();
  const disburse = useDisburseLoan();
  const [reason, setReason] = useState("");

  return (
    <li className="flex flex-col gap-2 rounded border border-border px-3 py-2 text-sm">
      <div className="flex items-center justify-between">
        <span className="font-medium text-foreground">
          {formatMinor(amountMinor)} &middot; {termMonths} months
        </span>
        <LoanApplicationStateBadge state={state} />
      </div>
      <span className="text-muted">Submitted {formatDate(createdAt)}</span>
      {decisionReason && <span className="text-muted">Decision: {decisionReason}</span>}

      {(decide.isError || disburse.isError) && (
        <Alert tone="danger">
          {decide.error instanceof ApiError
            ? decide.error.message
            : disburse.error instanceof ApiError
              ? disburse.error.message
              : "Action could not be completed."}
        </Alert>
      )}

      {canDecide && state === "ASSESSMENT" && (
        <div className="flex flex-wrap items-end gap-2">
          <Input
            label="Decision reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="min-w-[200px]"
          />
          <Button
            size="sm"
            loading={decide.isPending}
            onClick={() => decide.mutate({ id: applicationId, approve: true, reason: reason || "approved" })}
          >
            Approve
          </Button>
          <Button
            size="sm"
            variant="danger"
            loading={decide.isPending}
            onClick={() => decide.mutate({ id: applicationId, approve: false, reason: reason || "rejected" })}
          >
            Reject
          </Button>
        </div>
      )}

      {canDecide && state === "APPROVED" && (
        <Button size="sm" loading={disburse.isPending} onClick={() => disburse.mutate(applicationId)}>
          Disburse
        </Button>
      )}
    </li>
  );
}
