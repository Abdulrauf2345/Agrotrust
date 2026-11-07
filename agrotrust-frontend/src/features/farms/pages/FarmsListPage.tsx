import { Link } from "react-router-dom";
import { useMyFarms } from "../hooks";
import { verificationTone, verificationLabel } from "../utils";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { paths } from "@/routes/paths";

export function FarmsListPage() {
  const { data, isLoading } = useMyFarms();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">My farms</h1>
        <Link to={paths.farmNew}>
          <Button>Register farm</Button>
        </Link>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : !data?.length ? (
        <EmptyState title="No farms yet" description="Register your first farm to start listing crops against it." />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((farm) => (
            <Link key={farm.id} to={paths.farmDetail(farm.id)}>
              <Card className="h-full hover:shadow-md">
                <div className="mb-2 flex items-start justify-between">
                  <h3 className="font-semibold text-foreground">{farm.name}</h3>
                  <Badge tone={verificationTone(farm.verification_status)}>
                    {verificationLabel(farm.verification_status)}
                  </Badge>
                </div>
                <p className="text-sm text-muted">
                  {farm.lga}, {farm.state}
                </p>
                <p className="mt-2 text-sm text-foreground">{farm.size_hectares} ha</p>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
