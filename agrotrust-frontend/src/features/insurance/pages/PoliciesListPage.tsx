import { Link } from "react-router-dom";
import { usePolicies } from "../hooks";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { PolicyStateBadge } from "@/components/ui/StatusBadge";
import { formatMinor } from "@/lib/formatting/currency";
import { formatDate } from "@/lib/formatting/date";
import { paths } from "@/routes/paths";

export function PoliciesListPage() {
  const { data: policies, isLoading } = usePolicies();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Insurance policies</h1>
        <Link to={paths.insuranceBuy}>
          <Button size="sm">Buy a policy</Button>
        </Link>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : !policies?.length ? (
        <EmptyState
          title="No policies yet"
          description="Buy parametric weather cover for a farm to protect against drought losses."
        />
      ) : (
        <div className="overflow-hidden rounded border border-border">
          <table className="w-full text-sm">
            <thead className="bg-surface text-left text-muted">
              <tr>
                <th className="p-3">Coverage</th>
                <th className="p-3">Premium</th>
                <th className="p-3">Window</th>
                <th className="p-3">State</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((p) => (
                <tr key={p.id} className="border-t border-border hover:bg-surface">
                  <td className="p-3">
                    <Link to={paths.policyDetail(p.id)} className="text-primary hover:underline">
                      {formatMinor(p.coverage_minor)}
                    </Link>
                  </td>
                  <td className="p-3 text-muted">{formatMinor(p.premium_minor)}</td>
                  <td className="p-3 text-muted">
                    {formatDate(p.window_start)} &ndash; {formatDate(p.window_end)}
                  </td>
                  <td className="p-3">
                    <PolicyStateBadge state={p.state} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
