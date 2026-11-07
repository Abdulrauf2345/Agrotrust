import { useParams } from "react-router-dom";
import { useFarm, useRequestVerification } from "../hooks";
import { verificationTone, verificationLabel } from "../utils";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Skeleton } from "@/components/ui/Skeleton";

export function FarmDetailPage() {
  const { farmId = "" } = useParams();
  const { data: farm, isLoading } = useFarm(farmId);
  const requestVerification = useRequestVerification(farmId);

  if (isLoading) return <Skeleton className="h-64" />;
  if (!farm) return <Alert tone="danger">Farm not found.</Alert>;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-semibold text-foreground">{farm.name}</h1>
        <Badge tone={verificationTone(farm.verification_status)}>
          {verificationLabel(farm.verification_status)}
        </Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-muted">Location</dt>
            <dd className="font-medium text-foreground">
              {farm.lga}, {farm.state}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Size</dt>
            <dd className="font-medium text-foreground">{farm.size_hectares} ha</dd>
          </div>
          <div>
            <dt className="text-muted">Coordinates</dt>
            <dd className="font-medium text-foreground">
              {farm.lat}, {farm.lon}
            </dd>
          </div>
        </dl>
      </Card>

      {farm.verification_status === "UNVERIFIED" && (
        <Card>
          <p className="mb-3 text-sm text-muted">
            An unverified farm can still be used to back a listing, but verified farms are weighted higher in
            search and are required for most loan applications.
          </p>
          <Button onClick={() => requestVerification.mutate()} loading={requestVerification.isPending}>
            Request verification
          </Button>
        </Card>
      )}
    </div>
  );
}
