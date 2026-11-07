import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatMinor } from "@/lib/formatting/currency";
import { useEscrow } from "../hooks";

export function EscrowPanel({ orderId }: { orderId: string }) {
  const { data, isLoading } = useEscrow(orderId);

  if (isLoading) return <Skeleton className="h-40" />;
  if (!data) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Escrow</CardTitle>
        <Badge tone={data.state === "RELEASED" ? "success" : "primary"}>{data.state}</Badge>
      </CardHeader>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-muted">Held</dt>
          <dd className="font-medium text-foreground">{formatMinor(data.amount_minor, data.currency)}</dd>
        </div>
        <div>
          <dt className="text-muted">Paid to seller</dt>
          <dd className="font-medium text-foreground">{formatMinor(data.seller_minor, data.currency)}</dd>
        </div>
        <div>
          <dt className="text-muted">Platform fee</dt>
          <dd className="font-medium text-foreground">{formatMinor(data.fee_minor, data.currency)}</dd>
        </div>
        <div>
          <dt className="text-muted">Refunded to buyer</dt>
          <dd className="font-medium text-foreground">{formatMinor(data.refunded_minor, data.currency)}</dd>
        </div>
      </dl>
    </Card>
  );
}
