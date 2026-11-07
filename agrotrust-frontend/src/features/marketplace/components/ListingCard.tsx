import { Link } from "react-router-dom";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { paths } from "@/routes/paths";
import type { Listing } from "@/types/api";

export function ListingCard({ listing }: { listing: Listing }) {
  return (
    <Link to={paths.listingDetail(listing.id)}>
      <Card className="h-full transition-shadow hover:shadow-md">
        <div className="mb-2 flex items-start justify-between">
          <h3 className="font-semibold text-foreground">{listing.title}</h3>
          {listing.farm_verified === 1 && <Badge tone="success">Verified farm</Badge>}
        </div>
        <p className="text-sm text-muted">
          {listing.lga}, {listing.state}
        </p>
        <div className="mt-3 flex items-baseline justify-between">
          <span className="text-lg font-semibold text-primary">
            {listing.currency} {listing.price} / {listing.unit}
          </span>
          <span className="text-sm text-muted">{listing.quantity_available} available</span>
        </div>
      </Card>
    </Link>
  );
}
