import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useListing } from "../hooks";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Alert } from "@/components/ui/Alert";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAuth } from "@/lib/auth/AuthContext";
import { roleHasPermission } from "@/lib/auth/permissions";
import { createOrder } from "@/features/orders/api";
import { paths } from "@/routes/paths";
import { ApiError } from "@/lib/api/errors";

export function ListingDetailPage() {
  const { listingId = "" } = useParams();
  const { data: listing, isLoading } = useListing(listingId);
  const { user } = useAuth();
  const navigate = useNavigate();
  const canOrder = roleHasPermission(user?.roles ?? [], "order:create");

  const [quantity, setQuantity] = useState("");
  const [address, setAddress] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (isLoading) return <Skeleton className="h-64" />;
  if (!listing) return <Alert tone="danger">Listing not found.</Alert>;

  const handleOrder = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const order = await createOrder(listing.id, quantity, address);
      navigate(paths.orderDetail(order.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not place order. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-semibold text-foreground">{listing.title}</h1>
          {listing.farm_verified === 1 && <Badge tone="success">Verified farm</Badge>}
        </div>
        <p className="text-sm text-muted">
          {listing.lga}, {listing.state}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Listing details</CardTitle>
          </CardHeader>
          {listing.description && <p className="mb-3 text-sm text-foreground">{listing.description}</p>}
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-muted">Price</dt>
              <dd className="font-medium text-foreground">
                {listing.currency} {listing.price} / {listing.unit}
              </dd>
            </div>
            <div>
              <dt className="text-muted">Available</dt>
              <dd className="font-medium text-foreground">{listing.quantity_available}</dd>
            </div>
            <div>
              <dt className="text-muted">Quality grade</dt>
              <dd className="font-medium text-foreground">{listing.quality_grade}</dd>
            </div>
          </dl>
        </Card>

        {canOrder && (
          <Card>
            <CardHeader>
              <CardTitle>Place an order</CardTitle>
            </CardHeader>
            {error && (
              <div className="mb-3">
                <Alert tone="danger">{error}</Alert>
              </div>
            )}
            <div className="flex flex-col gap-3">
              <Input
                label={`Quantity (${listing.unit})`}
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                placeholder="e.g. 50"
              />
              <Input
                label="Delivery address"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="Where should this be delivered?"
              />
              <Button onClick={handleOrder} loading={submitting} disabled={!quantity}>
                Place order
              </Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
