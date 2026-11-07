import { useState } from "react";
import { useAuditTrail } from "../hooks";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatDateTime } from "@/lib/formatting/date";

export function AdminAuditPage() {
  const [resourceType, setResourceType] = useState("");
  const { data: entries, isLoading } = useAuditTrail({ resource_type: resourceType || undefined, limit: 200 });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-foreground">Audit log</h1>
      <Input
        label="Filter by resource type"
        placeholder="orders, loans, farms..."
        value={resourceType}
        onChange={(e) => setResourceType(e.target.value)}
        className="max-w-xs"
      />

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      ) : !entries?.length ? (
        <EmptyState title="No audit entries" description="Try clearing the filter or widening the search." />
      ) : (
        <div className="overflow-hidden rounded border border-border">
          <table className="w-full text-sm">
            <thead className="bg-surface text-left text-muted">
              <tr>
                <th className="p-3">When</th>
                <th className="p-3">Action</th>
                <th className="p-3">Resource</th>
                <th className="p-3">Actor</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} className="border-t border-border">
                  <td className="p-3 text-muted">{formatDateTime(e.at)}</td>
                  <td className="p-3 font-medium text-foreground">{e.action}</td>
                  <td className="p-3 text-muted">
                    {e.resource_type}
                    {e.resource_id ? ` / ${e.resource_id.slice(0, 8)}` : ""}
                  </td>
                  <td className="p-3 text-muted">{e.actor_id ? e.actor_id.slice(0, 8) : "system"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
