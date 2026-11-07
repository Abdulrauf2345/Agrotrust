import { useState } from "react";
import { Link } from "react-router-dom";
import { ListingCard } from "../components/ListingCard";
import { useListingSearch } from "../hooks";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { useAuth } from "@/lib/auth/AuthContext";
import { roleHasPermission } from "@/lib/auth/permissions";
import { paths } from "@/routes/paths";

export function MarketplaceListPage() {
  const { user } = useAuth();
  const canCreate = roleHasPermission(user?.roles ?? [], "listing:create");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const { data, isLoading } = useListingSearch({ q: query || undefined });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Marketplace</h1>
        {canCreate && (
          <Link to={paths.listingNew}>
            <Button>New listing</Button>
          </Link>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(search);
        }}
        className="flex gap-2"
      >
        <Input
          placeholder="Search crops, e.g. maize"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
      ) : !data?.items.length ? (
        <EmptyState title="No listings found" description="Try a different search, or check back later." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.items.map((listing) => (
            <ListingCard key={listing.id} listing={listing} />
          ))}
        </div>
      )}
    </div>
  );
}
