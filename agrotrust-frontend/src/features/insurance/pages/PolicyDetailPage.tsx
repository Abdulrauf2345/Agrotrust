import { useParams } from "react-router-dom";
import { usePayPremium, usePolicy } from "../hooks";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Skeleton } from "@/components/ui/Skeleton";
import { PolicyStateBadge } from "@/components/ui/StatusBadge";
import { formatMinor } from "@/lib/formatting/currency";
import { formatDate, formatDateTime } from "@/lib/formatting/date";
import { ApiError } from "@/lib/api/errors";

export function PolicyDetailPage() {
  const { policyId = "" } = useParams();
  const { data: policy, isLoading } = usePolicy(policyId);
  const payPremium = usePayPremium(policyId);

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!policy) return <Alert tone="danger">That policy could not be found.</Alert>;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Policy {policy.id.slice(0, 8)}</h1>
        <PolicyStateBadge state={policy.state} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Coverage</CardTitle>
        </CardHeader>
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-muted">Coverage</dt>
            <dd className="font-medium text-foreground">{formatMinor(policy.coverage_minor)}</dd>
          </div>
          <div>
            <dt className="text-muted">Premium</dt>
            <dd className="font-medium text-foreground">{formatMinor(policy.premium_minor)}</dd>
          </div>
          <div>
            <dt className="text-muted">Trigger</dt>
            <dd className="font-medium text-foreground">{policy.trigger_type}</dd>
          </div>
          <div>
            <dt className="text-muted">Cover window</dt>
            <dd className="font-medium text-foreground">
              {formatDate(policy.window_start)} &ndash; {formatDate(policy.window_end)}
            </dd>
          </div>
          {policy.premium_paid_at && (
            <div>
              <dt className="text-muted">Premium paid</dt>
              <dd className="font-medium text-foreground">{formatDateTime(policy.premium_paid_at)}</dd>
            </div>
          )}
        </dl>
      </Card>

      {policy.state === "PENDING_PAYMENT" && (
        <Card>
          <CardHeader>
            <CardTitle>Pay premium</CardTitle>
          </CardHeader>
          {payPremium.isError && (
            <Alert tone="danger" className="mb-3">
              {payPremium.error instanceof ApiError ? payPremium.error.message : "Could not pay the premium."}
            </Alert>
          )}
          <p className="mb-3 text-sm text-muted">
            Pay {formatMinor(policy.premium_minor)} from your wallet to activate this policy.
          </p>
          <Button loading={payPremium.isPending} onClick={() => payPremium.mutate()}>
            Pay {formatMinor(policy.premium_minor)}
          </Button>
        </Card>
      )}

      {policy.state === "TRIGGERED" && (
        <Alert tone="success">This policy's trigger condition was met and the payout has been released to your wallet.</Alert>
      )}
    </div>
  );
}
