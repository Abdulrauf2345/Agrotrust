import { useState } from "react";
import { useParams } from "react-router-dom";
import {
  useShipment,
  useShipmentTrack,
  useAssignShipment,
  useMarkPickedUp,
  useMarkInTransit,
  useMarkDelivered,
  useConfirmShipment,
  useMarkFailed,
} from "../hooks";
import { useVehicles, useDrivers } from "../hooks";
import { useMyOrganizations } from "@/features/organizations/hooks";
import { useOrder } from "@/features/orders/hooks";
import { ShipmentTrackTimeline } from "../components/ShipmentTrackTimeline";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Input } from "@/components/ui/Input";
import { Alert } from "@/components/ui/Alert";
import { Skeleton } from "@/components/ui/Skeleton";
import { ShipmentStateBadge } from "@/components/ui/StatusBadge";
import { useAuth } from "@/lib/auth/AuthContext";
import { ApiError } from "@/lib/api/errors";

export function ShipmentDetailPage() {
  const { shipmentId = "" } = useParams();
  const { user } = useAuth();
  const { data: shipment, isLoading } = useShipment(shipmentId);
  const { data: events, isLoading: eventsLoading } = useShipmentTrack(shipmentId);
  const { data: order } = useOrder(shipment?.order_id);
  const { data: orgs } = useMyOrganizations();
  const logisticsOrg = orgs?.find((o) => o.type === "LOGISTICS");
  const { data: vehicles } = useVehicles(logisticsOrg?.id);
  const { data: drivers } = useDrivers(logisticsOrg?.id);

  const [driverId, setDriverId] = useState("");
  const [vehicleId, setVehicleId] = useState("");
  const [failReason, setFailReason] = useState("");
  const [showFailForm, setShowFailForm] = useState(false);

  const assign = useAssignShipment();
  const pickedUp = useMarkPickedUp();
  const inTransit = useMarkInTransit();
  const delivered = useMarkDelivered();
  const confirm = useConfirmShipment();
  const failed = useMarkFailed();

  if (isLoading) return <Skeleton className="h-64" />;
  if (!shipment) return <Alert tone="danger">This shipment could not be found.</Alert>;

  const isBuyer = order && user?.id === order.buyer_id;
  const isProviderMember = logisticsOrg && shipment.provider_org_id === logisticsOrg.id;
  const anyPending =
    assign.isPending || pickedUp.isPending || inTransit.isPending || delivered.isPending || confirm.isPending || failed.isPending;
  const lastError = [assign, pickedUp, inTransit, delivered, confirm, failed].find((m) => m.isError)?.error;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Shipment {shipment.id.slice(0, 8)}</h1>
          <p className="text-sm text-muted">For order {shipment.order_id.slice(0, 8)}</p>
        </div>
        <ShipmentStateBadge state={shipment.state} />
      </div>

      {lastError && (
        <Alert tone="danger">{lastError instanceof ApiError ? lastError.message : "That action could not be completed."}</Alert>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Route</CardTitle>
          </CardHeader>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-muted">Pickup</dt>
              <dd className="font-medium text-foreground">
                {shipment.pickup_lat?.toFixed(4)}, {shipment.pickup_lon?.toFixed(4)}
              </dd>
            </div>
            <div>
              <dt className="text-muted">Dropoff</dt>
              <dd className="font-medium text-foreground">
                {shipment.dropoff_lat?.toFixed(4)}, {shipment.dropoff_lon?.toFixed(4)}
              </dd>
            </div>
          </dl>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Tracking</CardTitle>
          </CardHeader>
          {eventsLoading ? <Skeleton className="h-24" /> : <ShipmentTrackTimeline events={events ?? []} />}
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Actions</CardTitle>
        </CardHeader>
        <div className="flex flex-wrap items-end gap-3">
          {isProviderMember && shipment.state === "CREATED" && (
            <div className="flex flex-wrap items-end gap-2">
              <Select label="Driver" value={driverId} onChange={(e) => setDriverId(e.target.value)}>
                <option value="">Select a driver</option>
                {drivers?.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </Select>
              <Select label="Vehicle" value={vehicleId} onChange={(e) => setVehicleId(e.target.value)}>
                <option value="">Select a vehicle</option>
                {vehicles?.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.plate}
                  </option>
                ))}
              </Select>
              <Button
                disabled={!driverId || !vehicleId}
                loading={assign.isPending}
                onClick={() =>
                  assign.mutate([shipment.id, { driver_id: driverId, vehicle_id: vehicleId, provider_org_id: logisticsOrg!.id }])
                }
              >
                Assign
              </Button>
            </div>
          )}

          {isProviderMember && shipment.state === "ASSIGNED" && (
            <Button
              loading={pickedUp.isPending}
              onClick={() => pickedUp.mutate([shipment.id, shipment.pickup_lat ?? 0, shipment.pickup_lon ?? 0])}
            >
              Mark picked up
            </Button>
          )}

          {isProviderMember && shipment.state === "PICKED_UP" && (
            <Button loading={inTransit.isPending} onClick={() => inTransit.mutate([shipment.id])}>
              Mark in transit
            </Button>
          )}

          {isProviderMember && shipment.state === "IN_TRANSIT" && (
            <Button
              loading={delivered.isPending}
              onClick={() => delivered.mutate([shipment.id, shipment.dropoff_lat ?? 0, shipment.dropoff_lon ?? 0])}
            >
              Mark delivered
            </Button>
          )}

          {isBuyer && shipment.state === "DELIVERED" && (
            <Button loading={confirm.isPending} onClick={() => confirm.mutate([shipment.id])}>
              Confirm receipt
            </Button>
          )}

          {isProviderMember && !["CONFIRMED", "FAILED"].includes(shipment.state) && (
            <div className="flex items-end gap-2">
              {showFailForm ? (
                <>
                  <Input
                    label="Reason"
                    value={failReason}
                    onChange={(e) => setFailReason(e.target.value)}
                    placeholder="Vehicle breakdown, address not found..."
                  />
                  <Button
                    variant="danger"
                    disabled={!failReason}
                    loading={failed.isPending}
                    onClick={() => failed.mutate([shipment.id, failReason])}
                  >
                    Report failure
                  </Button>
                </>
              ) : (
                <Button variant="secondary" disabled={anyPending} onClick={() => setShowFailForm(true)}>
                  Report a failed delivery
                </Button>
              )}
            </div>
          )}
        </div>
        {!isProviderMember && !isBuyer && (
          <p className="text-sm text-muted">You are viewing this shipment as a party to its order, with no actions to take right now.</p>
        )}
      </Card>
    </div>
  );
}
