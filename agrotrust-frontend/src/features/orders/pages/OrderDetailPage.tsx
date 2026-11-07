import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useShipments } from "@/features/logistics/hooks";
import { ShipmentStateBadge } from "@/components/ui/StatusBadge";
import { paths } from "@/routes/paths";
import {
  useOrder,
  useConfirmOrder,
  useFundOrder,
  usePrepareOrder,
  useDispatchOrder,
  useMarkDelivered,
  useInspectOrder,
  useReleaseOrder,
  useCancelOrder,
  useOpenDispute,
} from "../hooks";
import { OrderTimeline } from "../components/OrderTimeline";
import { EscrowPanel } from "../components/EscrowPanel";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Alert } from "@/components/ui/Alert";
import { Skeleton } from "@/components/ui/Skeleton";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { formatMinor } from "@/lib/formatting/currency";
import { formatDateTime } from "@/lib/formatting/date";
import { useAuth } from "@/lib/auth/AuthContext";

export function OrderDetailPage() {
  const { orderId = "" } = useParams();
  const { user } = useAuth();
  const { data: order, isLoading, error } = useOrder(orderId);
  const { data: shipments } = useShipments();
  const shipment = shipments?.find((s) => s.order_id === orderId);

  const [deliveredQty, setDeliveredQty] = useState("");
  const [acceptedQty, setAcceptedQty] = useState("");
  const [qualityResult, setQualityResult] = useState("");
  const [activeAction, setActiveAction] = useState<"cancel" | "dispute" | null>(null);

  const confirm = useConfirmOrder(orderId);
  const fund = useFundOrder(orderId);
  const prepare = usePrepareOrder(orderId);
  const dispatch = useDispatchOrder(orderId);
  const markDelivered = useMarkDelivered(orderId);
  const inspect = useInspectOrder(orderId);
  const release = useReleaseOrder(orderId);
  const cancel = useCancelOrder(orderId);
  const dispute = useOpenDispute(orderId);

  if (isLoading) return <Skeleton className="h-64" />;
  if (error || !order) return <Alert tone="danger">This order could not be loaded.</Alert>;

  const isBuyer = user?.id === order.buyer_id;
  const isSeller = user?.id === order.seller_id;
  const anyActionPending =
    confirm.isPending ||
    fund.isPending ||
    prepare.isPending ||
    dispatch.isPending ||
    markDelivered.isPending ||
    inspect.isPending ||
    release.isPending;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Order {order.id.slice(0, 8)}</h1>
        <p className="text-sm text-muted">Placed {formatDateTime(order.created_at)}</p>
      </div>

      <Card>
        <OrderTimeline state={order.state} />
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-muted">Quantity</dt>
              <dd className="font-medium text-foreground">
                {order.qty_milli / 1000} {order.unit}
              </dd>
            </div>
            <div>
              <dt className="text-muted">Total</dt>
              <dd className="font-medium text-foreground">{formatMinor(order.total_minor, order.currency)}</dd>
            </div>
            {order.delivery_address && (
              <div className="col-span-2">
                <dt className="text-muted">Delivery address</dt>
                <dd className="font-medium text-foreground">{order.delivery_address}</dd>
              </div>
            )}
          </dl>
        </Card>

        <EscrowPanel orderId={order.id} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Shipment</CardTitle>
        </CardHeader>
        {shipment ? (
          <div className="flex items-center justify-between">
            <Link to={paths.shipmentDetail(shipment.id)} className="text-sm text-primary hover:underline">
              View shipment {shipment.id.slice(0, 8)}
            </Link>
            <ShipmentStateBadge state={shipment.state} />
          </div>
        ) : (isBuyer || isSeller) && ["FUNDED", "PREPARING"].includes(order.state) ? (
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted">No shipment requested yet for this order.</p>
            <Link to={paths.requestShipment(order.id)}>
              <Button size="sm" variant="secondary">
                Request a shipment
              </Button>
            </Link>
          </div>
        ) : (
          <p className="text-sm text-muted">No shipment for this order.</p>
        )}
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Actions</CardTitle>
        </CardHeader>
        <div className="flex flex-wrap items-start gap-3">
          {isSeller && order.state === "CREATED" && (
            <Button onClick={() => confirm.mutate()} loading={confirm.isPending}>
              Confirm order
            </Button>
          )}
          {isBuyer && order.state === "CONFIRMED" && (
            <Button onClick={() => fund.mutate()} loading={fund.isPending}>
              Fund escrow
            </Button>
          )}
          {isSeller && order.state === "FUNDED" && (
            <Button onClick={() => prepare.mutate()} loading={prepare.isPending}>
              Mark preparing
            </Button>
          )}
          {isSeller && order.state === "PREPARING" && (
            <Button onClick={() => dispatch.mutate()} loading={dispatch.isPending}>
              Dispatch
            </Button>
          )}
          {isSeller && order.state === "IN_TRANSIT" && (
            <div className="flex items-end gap-2">
              <Input
                label="Delivered quantity"
                value={deliveredQty}
                onChange={(e) => setDeliveredQty(e.target.value)}
                placeholder={`${order.qty_milli / 1000}`}
              />
              <Button
                onClick={() => markDelivered.mutate(deliveredQty)}
                loading={markDelivered.isPending}
                disabled={!deliveredQty}
              >
                Mark delivered
              </Button>
            </div>
          )}
          {isBuyer && order.state === "DELIVERED" && (
            <div className="flex flex-wrap items-end gap-2">
              <Input
                label="Accepted quantity"
                value={acceptedQty}
                onChange={(e) => setAcceptedQty(e.target.value)}
                placeholder={`${order.qty_milli / 1000}`}
              />
              <Input
                label="Quality notes (optional)"
                value={qualityResult}
                onChange={(e) => setQualityResult(e.target.value)}
              />
              <Button
                onClick={() => inspect.mutate({ acceptedQuantity: acceptedQty, qualityResult })}
                loading={inspect.isPending}
                disabled={!acceptedQty}
              >
                Confirm inspection
              </Button>
            </div>
          )}
          {isBuyer && order.state === "INSPECTED" && (
            <Button onClick={() => release.mutate()} loading={release.isPending}>
              Release escrow to seller
            </Button>
          )}
          {(isBuyer || isSeller) && !["COMPLETED", "CANCELLED", "DISPUTED"].includes(order.state) && (
            <Button variant="danger" onClick={() => setActiveAction("dispute")} disabled={anyActionPending}>
              Open dispute
            </Button>
          )}
          {(isBuyer || isSeller) && ["CREATED", "CONFIRMED"].includes(order.state) && (
            <Button variant="secondary" onClick={() => setActiveAction("cancel")} disabled={anyActionPending}>
              Cancel order
            </Button>
          )}
        </div>

        {activeAction === "cancel" && (
          <div className="mt-3">
            <ConfirmDialog
              title="Cancel this order? This cannot be undone."
              confirmLabel="Cancel order"
              onConfirm={async () => {
                await cancel.mutateAsync("Cancelled by user");
                setActiveAction(null);
              }}
              onCancel={() => setActiveAction(null)}
            />
          </div>
        )}
        {activeAction === "dispute" && (
          <div className="mt-3">
            <ConfirmDialog
              title="Open a dispute? An admin will review and decide the split."
              confirmLabel="Open dispute"
              onConfirm={async () => {
                await dispute.mutateAsync("Raised by user from order detail page");
                setActiveAction(null);
              }}
              onCancel={() => setActiveAction(null)}
            />
          </div>
        )}
      </Card>
    </div>
  );
}
