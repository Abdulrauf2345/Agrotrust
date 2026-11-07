import { KpiCard } from "@/components/ui/KpiCard";
import { useBuyerAnalytics } from "../hooks";
import { formatMinor } from "@/lib/formatting/currency";

export function BuyerDashboard() {
  const { data, isLoading } = useBuyerAnalytics();

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <KpiCard label="Total orders" value={data?.orders_total} loading={isLoading} />
      <KpiCard label="Completed" value={data?.orders_completed} loading={isLoading} />
      <KpiCard label="Disputed" value={data?.orders_disputed} loading={isLoading} />
      <KpiCard
        label="Total spend"
        value={data ? formatMinor(data.total_spend_minor) : undefined}
        loading={isLoading}
      />
    </div>
  );
}
