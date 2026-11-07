import { useState } from "react";
import { Link } from "react-router-dom";
import { useMyOrders } from "../hooks";
import { OrderStateBadge } from "@/components/ui/StatusBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatMinor } from "@/lib/formatting/currency";
import { formatDate } from "@/lib/formatting/date";
import { paths } from "@/routes/paths";
import { cn } from "@/lib/utilities/cn";

export function OrdersListPage() {
  const [role, setRole] = useState<"buyer" | "seller">("buyer");
  const { data, isLoading } = useMyOrders(role);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-foreground">Orders</h1>

      <div className="flex gap-1 rounded border border-border bg-surface p-1 w-fit">
        {(["buyer", "seller"] as const).map((r) => (
          <button
            key={r}
            onClick={() => setRole(r)}
            className={cn(
              "rounded px-3 py-1.5 text-sm font-medium capitalize",
              role === r ? "bg-primary text-primary-foreground" : "text-muted hover:text-foreground",
            )}
          >
            As {r}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : !data?.length ? (
        <EmptyState title="No orders yet" description={`Orders you place or receive as ${role} will show here.`} />
      ) : (
        <div className="overflow-hidden rounded border border-border">
          <table className="w-full text-sm">
            <thead className="bg-surface text-left text-muted">
              <tr>
                <th className="p-3">Order</th>
                <th className="p-3">Total</th>
                <th className="p-3">State</th>
                <th className="p-3">Created</th>
              </tr>
            </thead>
            <tbody>
              {data.map((order) => (
                <tr key={order.id} className="border-t border-border hover:bg-surface">
                  <td className="p-3">
                    <Link to={paths.orderDetail(order.id)} className="text-primary hover:underline">
                      {order.id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="p-3">{formatMinor(order.total_minor, order.currency)}</td>
                  <td className="p-3">
                    <OrderStateBadge state={order.state} />
                  </td>
                  <td className="p-3 text-muted">{formatDate(order.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
