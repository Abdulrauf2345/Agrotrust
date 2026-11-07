import { useState } from "react";
import { useAdminDisputes, useResolveDispute } from "../hooks";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { DisputeStateBadge } from "@/components/ui/StatusBadge";
import { formatDate } from "@/lib/formatting/date";
import { ApiError } from "@/lib/api/errors";
import type { DisputeState } from "@/types/api";

export function AdminDisputesPage() {
  const { data: disputes, isLoading } = useAdminDisputes();

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-foreground">Disputes</h1>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : !disputes?.length ? (
        <EmptyState title="No disputes" description="Open disputes on orders you can act on will show here." />
      ) : (
        <div className="flex flex-col gap-3">
          {disputes.map((d) => (
            <DisputeCard key={d.id} id={d.id} orderId={d.order_id} reason={d.reason} state={d.state}
              resolution={d.resolution} openedAt={d.opened_at} />
          ))}
        </div>
      )}
    </div>
  );
}

function DisputeCard({
  id,
  orderId,
  reason,
  state,
  resolution,
  openedAt,
}: {
  id: string;
  orderId: string;
  reason: string;
  state: DisputeState;
  resolution: string | null;
  openedAt: string;
}) {
  const resolveDispute = useResolveDispute();
  const [sellerAmount, setSellerAmount] = useState("");
  const [buyerAmount, setBuyerAmount] = useState("");
  const [note, setNote] = useState("");

  return (
    <Card>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium text-foreground">Order {orderId.slice(0, 8)}</span>
        <DisputeStateBadge state={state} />
      </div>
      <p className="mb-1 text-sm text-muted">Opened {formatDate(openedAt)}</p>
      <p className="mb-3 text-sm text-foreground">{reason}</p>
      {resolution && <p className="mb-3 text-sm text-muted">Resolution: {resolution}</p>}

      {state === "OPEN" && (
        <div className="flex flex-col gap-3 border-t border-border pt-3">
          {resolveDispute.isError && (
            <Alert tone="danger">
              {resolveDispute.error instanceof ApiError ? resolveDispute.error.message : "Could not resolve the dispute."}
            </Alert>
          )}
          <div className="flex flex-wrap items-end gap-3">
            <Input label="Seller gets (kobo)" value={sellerAmount} onChange={(e) => setSellerAmount(e.target.value)} />
            <Input label="Buyer refund (kobo)" value={buyerAmount} onChange={(e) => setBuyerAmount(e.target.value)} />
            <Input label="Resolution note" value={note} onChange={(e) => setNote(e.target.value)} className="min-w-[200px]" />
            <Button
              size="sm"
              loading={resolveDispute.isPending}
              onClick={() =>
                resolveDispute.mutate({
                  id,
                  seller_amount_minor: Number(sellerAmount) || 0,
                  buyer_amount_minor: Number(buyerAmount) || 0,
                  resolution: note,
                })
              }
            >
              Resolve
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
