import { Link } from "react-router-dom";
import { useState } from "react";
import { useAdminUsers } from "../hooks";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { Badge } from "@/components/ui/Badge";
import { formatDate } from "@/lib/formatting/date";
import { paths } from "@/routes/paths";

const STATUS_TONE: Record<string, "neutral" | "success" | "warning" | "danger" | "primary"> = {
  PENDING: "neutral",
  ACTIVE: "success",
  SUSPENDED: "warning",
  DELETED: "danger",
};

export function AdminUsersPage() {
  const [status, setStatus] = useState("");
  const { data, isLoading } = useAdminUsers({ status: status || undefined, limit: 100 });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-foreground">Users</h1>
      <Input
        label="Filter by status"
        placeholder="ACTIVE, PENDING, SUSPENDED, DELETED"
        value={status}
        onChange={(e) => setStatus(e.target.value.toUpperCase())}
        className="max-w-xs"
      />

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-14" />
          ))}
        </div>
      ) : !data?.items.length ? (
        <EmptyState title="No users found" description="Try a different status filter." />
      ) : (
        <div className="overflow-hidden rounded border border-border">
          <table className="w-full text-sm">
            <thead className="bg-surface text-left text-muted">
              <tr>
                <th className="p-3">Name</th>
                <th className="p-3">Phone</th>
                <th className="p-3">Status</th>
                <th className="p-3">Joined</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((u) => (
                <tr key={u.id} className="border-t border-border hover:bg-surface">
                  <td className="p-3">
                    <Link to={paths.adminUserDetail(u.id)} className="text-primary hover:underline">
                      {u.full_name ?? u.phone}
                    </Link>
                  </td>
                  <td className="p-3 text-muted">{u.phone}</td>
                  <td className="p-3">
                    <Badge tone={STATUS_TONE[u.status] ?? "neutral"}>{u.status}</Badge>
                  </td>
                  <td className="p-3 text-muted">{formatDate(u.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-border bg-surface p-2 text-xs text-muted">
            Showing {data.items.length} of {data.total} users
          </p>
        </div>
      )}
    </div>
  );
}
