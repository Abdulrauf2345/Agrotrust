import { useState } from "react";
import { useParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useLoan, useLoanSchedule, useRepayLoan } from "../hooks";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { LoanStateBadge } from "@/components/ui/StatusBadge";
import { formatMinor } from "@/lib/formatting/currency";
import { formatDate } from "@/lib/formatting/date";
import { numberInRange } from "@/lib/validation/shared";
import { ApiError } from "@/lib/api/errors";

const schema = z.object({
  amount_minor: numberInRange({ min: 1, message: "Enter an amount to repay" }),
});
type FormValues = z.infer<typeof schema>;

const INSTALLMENT_TONE: Record<string, "neutral" | "success" | "warning" | "danger" | "primary"> = {
  PENDING: "neutral",
  PARTIAL: "warning",
  PAID: "success",
  OVERDUE: "danger",
  SUPERSEDED: "neutral",
};

export function LoanDetailPage() {
  const { loanId = "" } = useParams();
  const { data: loan, isLoading } = useLoan(loanId);
  const { data: schedule, isLoading: scheduleLoading } = useLoanSchedule(loanId);
  const repay = useRepayLoan(loanId);
  const [justRepaid, setJustRepaid] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    await repay.mutateAsync(Number(values.amount_minor));
    setJustRepaid(true);
    reset();
  };

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!loan) return <Alert tone="danger">That loan could not be found.</Alert>;

  const outstandingPrincipal = schedule
    ? schedule.reduce((sum, r) => sum + (r.principal_due_minor - r.principal_paid_minor), 0)
    : null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Loan {loan.id.slice(0, 8)}</h1>
        <LoanStateBadge state={loan.state} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Summary</CardTitle>
        </CardHeader>
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-muted">Principal</dt>
            <dd className="font-medium text-foreground">{formatMinor(loan.principal_minor)}</dd>
          </div>
          <div>
            <dt className="text-muted">Term</dt>
            <dd className="font-medium text-foreground">{loan.term_months} months</dd>
          </div>
          <div>
            <dt className="text-muted">Rate</dt>
            <dd className="font-medium text-foreground">{(loan.annual_rate_bps / 100).toFixed(2)}% p.a.</dd>
          </div>
          <div>
            <dt className="text-muted">Disbursed</dt>
            <dd className="font-medium text-foreground">{formatDate(loan.disbursed_at)}</dd>
          </div>
          {outstandingPrincipal !== null && (
            <div>
              <dt className="text-muted">Outstanding principal</dt>
              <dd className="font-medium text-foreground">{formatMinor(outstandingPrincipal)}</dd>
            </div>
          )}
        </dl>
      </Card>

      {loan.state !== "COMPLETED" && (
        <Card>
          <CardHeader>
            <CardTitle>Make a repayment</CardTitle>
          </CardHeader>
          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-wrap items-end gap-3" noValidate>
            {repay.isError && (
              <Alert tone="danger" className="w-full">
                {repay.error instanceof ApiError ? repay.error.message : "Could not record the repayment."}
              </Alert>
            )}
            {justRepaid && !repay.isError && (
              <Alert tone="success" className="w-full">
                Repayment recorded.
              </Alert>
            )}
            <Input
              label="Amount (kobo)"
              error={errors.amount_minor?.message}
              {...register("amount_minor")}
            />
            <Button type="submit" loading={isSubmitting}>
              Repay
            </Button>
          </form>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Repayment schedule</CardTitle>
        </CardHeader>
        {scheduleLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : !schedule?.length ? (
          <p className="text-sm text-muted">No schedule available.</p>
        ) : (
          <div className="overflow-hidden rounded border border-border">
            <table className="w-full text-sm">
              <thead className="bg-surface text-left text-muted">
                <tr>
                  <th className="p-2">#</th>
                  <th className="p-2">Due date</th>
                  <th className="p-2">Principal</th>
                  <th className="p-2">Interest</th>
                  <th className="p-2">Penalty</th>
                  <th className="p-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {schedule.map((r) => (
                  <tr key={r.id} className="border-t border-border">
                    <td className="p-2">{r.installment_no}</td>
                    <td className="p-2 text-muted">{formatDate(r.due_date)}</td>
                    <td className="p-2">
                      {formatMinor(r.principal_paid_minor)} / {formatMinor(r.principal_due_minor)}
                    </td>
                    <td className="p-2">
                      {formatMinor(r.interest_paid_minor)} / {formatMinor(r.interest_due_minor)}
                    </td>
                    <td className="p-2">{r.penalty_minor > 0 ? formatMinor(r.penalty_minor) : "-"}</td>
                    <td className="p-2">
                      <Badge tone={INSTALLMENT_TONE[r.status] ?? "neutral"}>{r.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
