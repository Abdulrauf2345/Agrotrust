import { Link } from "react-router-dom";
import { useState } from "react";
import { useLots } from "../hooks";
import { useMyFarms } from "@/features/farms/hooks";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { formatMilli } from "@/lib/formatting/currency";
import { formatDate } from "@/lib/formatting/date";
import { paths } from "@/routes/paths";

const GRADE_TONE: Record<string, "neutral" | "success" | "warning" | "danger" | "primary"> = {
  A: "success",
  B: "primary",
  C: "warning",
  REJECT: "danger",
  UNGRADED: "neutral",
};

export function LotsListPage() {
  const { data: farms } = useMyFarms();
  const [farmId, setFarmId] = useState<string>("");
  const { data: lots, isLoading } = useLots(farmId || undefined);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Crop lots</h1>
        <Link to={paths.lotNew}>
          <Button size="sm">New lot</Button>
        </Link>
      </div>

      {farms && farms.length > 0 && (
        <Select value={farmId} onChange={(e) => setFarmId(e.target.value)} className="max-w-xs">
          <option value="">All my farms</option>
          {farms.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </Select>
      )}

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : !lots?.length ? (
        <EmptyState title="No lots yet" description="Record a harvest to start a lot's custody chain." />
      ) : (
        <div className="overflow-hidden rounded border border-border">
          <table className="w-full text-sm">
            <thead className="bg-surface text-left text-muted">
              <tr>
                <th className="p-3">Code</th>
                <th className="p-3">Quantity</th>
                <th className="p-3">Grade</th>
                <th className="p-3">Harvested</th>
              </tr>
            </thead>
            <tbody>
              {lots.map((lot) => (
                <tr key={lot.id} className="border-t border-border hover:bg-surface">
                  <td className="p-3">
                    <Link to={paths.lotDetail(lot.id)} className="text-primary hover:underline">
                      {lot.code}
                    </Link>
                  </td>
                  <td className="p-3 text-muted">{formatMilli(lot.quantity_milli, ` ${lot.unit}`)}</td>
                  <td className="p-3">
                    <Badge tone={GRADE_TONE[lot.quality_grade] ?? "neutral"}>{lot.quality_grade}</Badge>
                  </td>
                  <td className="p-3 text-muted">{formatDate(lot.harvest_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
