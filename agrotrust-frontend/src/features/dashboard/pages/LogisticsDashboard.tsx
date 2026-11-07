import { Link } from "react-router-dom";
import { KpiCard } from "@/components/ui/KpiCard";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ShipmentStateBadge } from "@/components/ui/StatusBadge";
import { useShipments } from "@/features/logistics/hooks";
import { useVehicles, useDrivers } from "@/features/logistics/hooks";
import { useMyOrganizations } from "@/features/organizations/hooks";
import { formatDate } from "@/lib/formatting/date";
import { paths } from "@/routes/paths";

// There is no /api/v1/analytics/logistics route on the backend (only
// farmer, buyer, and platform analytics exist), so this dashboard is built
// from the same list endpoints the Fleet and Shipments pages already use
// rather than inventing a summary the backend does not actually compute.
export function LogisticsDashboard() {
  const { data: orgs, isLoading: orgsLoading } = useMyOrganizations();
  const logisticsOrg = orgs?.find((o) => o.type === "LOGISTICS");
  const { data: shipments, isLoading: shipmentsLoading } = useShipments();
  const { data: vehicles, isLoading: vehiclesLoading } = useVehicles(logisticsOrg?.id);
  const { data: drivers, isLoading: driversLoading } = useDrivers(logisticsOrg?.id);

  if (!orgsLoading && !logisticsOrg) {
    return (
      <EmptyState
        title="No logistics organization yet"
        description="Create a logistics organization from the Organizations screen, then register vehicles and drivers on the Fleet page to start carrying shipments."
      />
    );
  }

  const active = shipments?.filter((s) => !["CONFIRMED", "FAILED"].includes(s.state)) ?? [];
  const needsAssignment = shipments?.filter((s) => s.state === "CREATED") ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="Active shipments" value={active.length} loading={shipmentsLoading} />
        <KpiCard label="Awaiting assignment" value={needsAssignment.length} loading={shipmentsLoading} />
        <KpiCard label="Vehicles" value={vehicles?.length} loading={vehiclesLoading} />
        <KpiCard label="Drivers" value={drivers?.length} loading={driversLoading} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Shipments needing a driver</CardTitle>
        </CardHeader>
        {needsAssignment.length === 0 ? (
          <p className="text-sm text-muted">Nothing waiting on assignment right now.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {needsAssignment.map((s) => (
              <li key={s.id} className="flex items-center justify-between rounded border border-border px-3 py-2 text-sm">
                <Link to={paths.shipmentDetail(s.id)} className="text-primary hover:underline">
                  {s.id.slice(0, 8)}
                </Link>
                <span className="text-muted">{formatDate(s.created_at)}</span>
                <ShipmentStateBadge state={s.state} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
