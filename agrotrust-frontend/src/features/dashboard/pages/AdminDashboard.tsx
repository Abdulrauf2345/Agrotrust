import { KpiCard } from "@/components/ui/KpiCard";
import { usePlatformAnalytics } from "../hooks";
import { QuickLinks } from "../components/QuickLinks";
import { formatMinor } from "@/lib/formatting/currency";
import { paths } from "@/routes/paths";

export function AdminDashboard() {
  const { data, isLoading } = usePlatformAnalytics();

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="Active users" value={data?.active_users} loading={isLoading} />
        <KpiCard label="Farms" value={data?.farms_total} loading={isLoading} />
        <KpiCard label="Verified farms" value={data?.farms_verified} loading={isLoading} />
        <KpiCard label="Open disputes" value={data?.open_disputes} loading={isLoading} />
        <KpiCard
          label="Gross merchandise value"
          value={data ? formatMinor(data.gross_merchandise_value_minor) : undefined}
          loading={isLoading}
        />
        <KpiCard
          label="Platform fee revenue"
          value={data ? formatMinor(data.platform_fee_revenue_minor) : undefined}
          loading={isLoading}
        />
      </div>
      <QuickLinks
        links={[
          { label: "Users", to: paths.adminUsers, description: "Search and review platform users." },
          { label: "Disputes", to: paths.adminDisputes, description: "Resolve open order disputes." },
          { label: "Audit log", to: paths.adminAudit, description: "Inspect the tamper-evident audit trail." },
        ]}
      />
    </div>
  );
}
