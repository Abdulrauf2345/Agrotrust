import { useAuth } from "@/lib/auth/AuthContext";
import { primaryRole } from "@/lib/auth/permissions";
import { FarmerDashboard } from "./FarmerDashboard";
import { BuyerDashboard } from "./BuyerDashboard";
import { AdminDashboard } from "./AdminDashboard";
import { LogisticsDashboard } from "./LogisticsDashboard";
import { LenderDashboard } from "./LenderDashboard";
import { GenericDashboard } from "./GenericDashboard";

const DASHBOARD_ROLES = ["FARMER", "BUYER", "PLATFORM_ADMIN", "LOGISTICS_PROVIDER", "LENDER"] as const;

export function DashboardPage() {
  const { user } = useAuth();
  const role = primaryRole(user?.roles ?? []);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-foreground">
        Welcome back{user ? `, ${user.full_name.split(" ")[0]}` : ""}
      </h1>
      {role === "FARMER" && <FarmerDashboard />}
      {role === "BUYER" && <BuyerDashboard />}
      {role === "PLATFORM_ADMIN" && <AdminDashboard />}
      {role === "LOGISTICS_PROVIDER" && <LogisticsDashboard />}
      {role === "LENDER" && <LenderDashboard />}
      {(!role || !DASHBOARD_ROLES.includes(role as (typeof DASHBOARD_ROLES)[number])) && <GenericDashboard />}
    </div>
  );
}
