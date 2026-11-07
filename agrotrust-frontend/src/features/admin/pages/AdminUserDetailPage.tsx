import { useParams } from "react-router-dom";
import { useAdminUserDetail } from "../hooks";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Alert } from "@/components/ui/Alert";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDateTime } from "@/lib/formatting/date";

export function AdminUserDetailPage() {
  const { userId = "" } = useParams();
  const { data: user, isLoading } = useAdminUserDetail(userId);

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!user) return <Alert tone="danger">That user could not be found.</Alert>;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">{user.full_name ?? user.phone}</h1>

      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
        </CardHeader>
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-muted">Phone</dt>
            <dd className="font-medium text-foreground">{user.phone}</dd>
          </div>
          <div>
            <dt className="text-muted">Email</dt>
            <dd className="font-medium text-foreground">{user.email ?? "-"}</dd>
          </div>
          <div>
            <dt className="text-muted">Status</dt>
            <dd className="font-medium text-foreground">{user.status}</dd>
          </div>
          <div>
            <dt className="text-muted">Joined</dt>
            <dd className="font-medium text-foreground">{formatDateTime(user.created_at)}</dd>
          </div>
          {user.kyc && (
            <div>
              <dt className="text-muted">KYC</dt>
              <dd className="font-medium text-foreground">{user.kyc.status}</dd>
            </div>
          )}
        </dl>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Roles</CardTitle>
        </CardHeader>
        {user.roles.length === 0 ? (
          <p className="text-sm text-muted">No roles assigned.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {user.roles.map((r) => (
              <Badge key={r} tone="primary">
                {r}
              </Badge>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Organizations</CardTitle>
        </CardHeader>
        {user.organizations.length === 0 ? (
          <p className="text-sm text-muted">Not a member of any organization.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {user.organizations.map((o) => (
              <li key={o.org_id} className="flex items-center justify-between rounded border border-border px-3 py-2 text-sm">
                <span className="text-muted">{o.org_id.slice(0, 8)}</span>
                <Badge tone="neutral">{o.role}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
