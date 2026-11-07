import { Card } from "./Card";
import { Skeleton } from "./Skeleton";

export function KpiCard({
  label,
  value,
  loading,
}: {
  label: string;
  value: string | number | null | undefined;
  loading?: boolean;
}) {
  return (
    <Card>
      <p className="text-sm text-muted">{label}</p>
      {loading ? (
        <Skeleton className="mt-2 h-7 w-20" />
      ) : (
        <p className="mt-1 text-2xl font-semibold text-foreground">{value ?? "-"}</p>
      )}
    </Card>
  );
}
