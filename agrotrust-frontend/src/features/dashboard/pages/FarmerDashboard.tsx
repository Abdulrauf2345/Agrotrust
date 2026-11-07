import { KpiCard } from "@/components/ui/KpiCard";
import { useMyAnalytics } from "../hooks";
import { QuickLinks } from "../components/QuickLinks";
import { formatMinor } from "@/lib/formatting/currency";
import { paths } from "@/routes/paths";

export function FarmerDashboard() {
  const { data, isLoading } = useMyAnalytics();

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="Farms" value={data?.farms_total} loading={isLoading} />
        <KpiCard label="Verified farms" value={data?.farms_verified} loading={isLoading} />
        <KpiCard label="Active listings" value={data?.active_listings} loading={isLoading} />
        <KpiCard label="Completed sales" value={data?.completed_sales} loading={isLoading} />
        <KpiCard
          label="Sales revenue"
          value={data ? formatMinor(data.sales_revenue_minor) : undefined}
          loading={isLoading}
        />
        <KpiCard label="Active loans" value={data?.active_loans} loading={isLoading} />
        <KpiCard
          label="Active loan principal"
          value={data ? formatMinor(data.active_loan_principal_minor) : undefined}
          loading={isLoading}
        />
      </div>
      <QuickLinks
        links={[
          { label: "Apply for a loan", to: paths.lending, description: "Browse loan products and apply for financing." },
          { label: "Insure a farm", to: paths.insurance, description: "Buy a rainfall-indexed policy and protect against drought." },
          { label: "Track my lots", to: paths.traceability, description: "Record harvests, weighing and inspections." },
        ]}
      />
    </div>
  );
}
