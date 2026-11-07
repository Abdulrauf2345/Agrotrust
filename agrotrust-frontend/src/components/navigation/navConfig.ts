import { Home, Sprout, Store, Package, Bell, Truck, Building2, Landmark, QrCode, ShieldCheck, Users, ScrollText, Gavel } from "lucide-react";
import { paths } from "@/routes/paths";
import type { Role } from "@/types/api";

export interface NavItem {
  label: string;
  to: string;
  icon: typeof Home;
  roles?: Role[];
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", to: paths.dashboard, icon: Home },
  {
    label: "Farms",
    to: paths.farms,
    icon: Sprout,
    roles: ["FARMER", "COOPERATIVE_ADMIN", "AGGREGATOR", "FIELD_AGENT", "PLATFORM_ADMIN"],
  },
  { label: "Marketplace", to: paths.marketplace, icon: Store },
  { label: "Orders", to: paths.orders, icon: Package },
  { label: "Shipments", to: paths.shipments, icon: Truck },
  { label: "Organizations", to: paths.organizations, icon: Building2 },
  {
    label: "Fleet",
    to: paths.fleet,
    icon: Truck,
    roles: ["LOGISTICS_PROVIDER", "PLATFORM_ADMIN"],
  },
  { label: "Lending", to: paths.lending, icon: Landmark },
  { label: "Traceability", to: paths.traceability, icon: QrCode },
  { label: "Insurance", to: paths.insurance, icon: ShieldCheck },
  { label: "Notifications", to: paths.notifications, icon: Bell },
  { label: "Admin: Users", to: paths.adminUsers, icon: Users, roles: ["PLATFORM_ADMIN"] },
  { label: "Admin: Disputes", to: paths.adminDisputes, icon: Gavel, roles: ["PLATFORM_ADMIN"] },
  { label: "Admin: Audit log", to: paths.adminAudit, icon: ScrollText, roles: ["PLATFORM_ADMIN"] },
];
