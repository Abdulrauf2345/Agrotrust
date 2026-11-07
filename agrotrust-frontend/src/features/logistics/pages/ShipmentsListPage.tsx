import { Link } from "react-router-dom";
import { useShipments } from "../hooks";
import { ShipmentStateBadge } from "@/components/ui/StatusBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatDate } from "@/lib/formatting/date";
import { paths } from "@/routes/paths";

export function ShipmentsListPage() {
  const { data, isLoading } = useShipments();

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-foreground">Shipments</h1>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : !data?.length ? (
        <EmptyState
          title="No shipments yet"
          description="Shipments for orders you buy, sell, or carry will show here."
        />
      ) : (
        <div className="overflow-hidden rounded border border-border">
          <table className="w-full text-sm">
            <thead className="bg-surface text-left text-muted">
              <tr>
                <th className="p-3">Shipment</th>
                <th className="p-3">Order</th>
                <th className="p-3">State</th>
                <th className="p-3">Updated</th>
              </tr>
            </thead>
            <tbody>
              {data.map((shipment) => (
                <tr key={shipment.id} className="border-t border-border hover:bg-surface">
                  <td className="p-3">
                    <Link to={paths.shipmentDetail(shipment.id)} className="text-primary hover:underline">
                      {shipment.id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="p-3 text-muted">{shipment.order_id.slice(0, 8)}</td>
                  <td className="p-3">
                    <ShipmentStateBadge state={shipment.state} />
                  </td>
                  <td className="p-3 text-muted">{formatDate(shipment.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
