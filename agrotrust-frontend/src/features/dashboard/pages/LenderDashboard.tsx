import { useLoanApplications, useLoans } from "@/features/lending/hooks";
import { KpiCard } from "@/components/ui/KpiCard";
import { QuickLinks } from "../components/QuickLinks";
import { formatMinor } from "@/lib/formatting/currency";
import { paths } from "@/routes/paths";

export function LenderDashboard() {
  const { data: applications, isLoading: applicationsLoading } = useLoanApplications();
  const { data: loans, isLoading: loansLoading } = useLoans();

  const pendingCount = applications?.filter((a) => a.state === "ASSESSMENT").length ?? 0;
  const activeLoans = loans?.filter((l) => l.state === "ACTIVE" || l.state === "REPAYING") ?? [];
  const outstandingPrincipal = activeLoans.reduce((sum, l) => sum + l.principal_minor, 0);

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="Pending applications" value={pendingCount} loading={applicationsLoading} />
        <KpiCard label="Active loans" value={activeLoans.length} loading={loansLoading} />
        <KpiCard
          label="Outstanding principal"
          value={loansLoading ? undefined : formatMinor(outstandingPrincipal)}
          loading={loansLoading}
        />
        <KpiCard label="Total applications" value={applications?.length} loading={applicationsLoading} />
      </div>
      <QuickLinks
        links={[
          { label: "Loan products", to: paths.lending, description: "List a product or review what's available." },
          { label: "Applications & loans", to: paths.lendingApplications, description: "Decide on applications and disburse approved loans." },
        ]}
      />
    </div>
  );
}
