import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShellLayout } from "@/app/layouts/AppShellLayout";
import { AuthLayout } from "@/app/layouts/AuthLayout";
import { ProtectedRoute } from "./ProtectedRoute";
import { NotFoundPage } from "@/app/pages/NotFoundPage";
import { LoginPage } from "@/features/auth/pages/LoginPage";
import { RegisterPage } from "@/features/auth/pages/RegisterPage";
import { DashboardPage } from "@/features/dashboard/pages/DashboardPage";
import { FarmsListPage } from "@/features/farms/pages/FarmsListPage";
import { FarmCreatePage } from "@/features/farms/pages/FarmCreatePage";
import { FarmDetailPage } from "@/features/farms/pages/FarmDetailPage";
import { MarketplaceListPage } from "@/features/marketplace/pages/MarketplaceListPage";
import { CreateListingPage } from "@/features/marketplace/pages/CreateListingPage";
import { ListingDetailPage } from "@/features/marketplace/pages/ListingDetailPage";
import { OrdersListPage } from "@/features/orders/pages/OrdersListPage";
import { OrderDetailPage } from "@/features/orders/pages/OrderDetailPage";
import { NotificationsPage } from "@/features/notifications/pages/NotificationsPage";
import { OrganizationsPage } from "@/features/organizations/pages/OrganizationsPage";
import { FleetPage } from "@/features/logistics/pages/FleetPage";
import { ShipmentsListPage } from "@/features/logistics/pages/ShipmentsListPage";
import { ShipmentDetailPage } from "@/features/logistics/pages/ShipmentDetailPage";
import { RequestShipmentPage } from "@/features/logistics/pages/RequestShipmentPage";
import { LoanProductsPage } from "@/features/lending/pages/LoanProductsPage";
import { LoanApplyPage } from "@/features/lending/pages/LoanApplyPage";
import { LoanApplicationsPage } from "@/features/lending/pages/LoanApplicationsPage";
import { LoanDetailPage } from "@/features/lending/pages/LoanDetailPage";
import { LotsListPage } from "@/features/traceability/pages/LotsListPage";
import { LotCreatePage } from "@/features/traceability/pages/LotCreatePage";
import { LotDetailPage } from "@/features/traceability/pages/LotDetailPage";
import { PoliciesListPage } from "@/features/insurance/pages/PoliciesListPage";
import { PolicyBuyPage } from "@/features/insurance/pages/PolicyBuyPage";
import { PolicyDetailPage } from "@/features/insurance/pages/PolicyDetailPage";
import { AdminUsersPage } from "@/features/admin/pages/AdminUsersPage";
import { AdminUserDetailPage } from "@/features/admin/pages/AdminUserDetailPage";
import { AdminAuditPage } from "@/features/admin/pages/AdminAuditPage";
import { AdminDisputesPage } from "@/features/admin/pages/AdminDisputesPage";
import { paths } from "@/routes/paths";

export const router = createBrowserRouter([
  {
    element: <AuthLayout />,
    children: [
      { path: paths.login, element: <LoginPage /> },
      { path: paths.register, element: <RegisterPage /> },
    ],
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppShellLayout />,
        children: [
          { path: "/", element: <Navigate to={paths.dashboard} replace /> },
          { path: paths.dashboard, element: <DashboardPage /> },
          { path: paths.farms, element: <FarmsListPage /> },
          { path: paths.farmNew, element: <FarmCreatePage /> },
          { path: "/farms/:farmId", element: <FarmDetailPage /> },
          { path: paths.marketplace, element: <MarketplaceListPage /> },
          { path: paths.listingNew, element: <CreateListingPage /> },
          { path: "/marketplace/:listingId", element: <ListingDetailPage /> },
          { path: paths.orders, element: <OrdersListPage /> },
          { path: "/orders/:orderId", element: <OrderDetailPage /> },
          { path: "/orders/:orderId/shipment/new", element: <RequestShipmentPage /> },
          { path: paths.organizations, element: <OrganizationsPage /> },
          { path: paths.fleet, element: <FleetPage /> },
          { path: paths.shipments, element: <ShipmentsListPage /> },
          { path: "/shipments/:shipmentId", element: <ShipmentDetailPage /> },
          { path: paths.notifications, element: <NotificationsPage /> },
          { path: paths.lending, element: <LoanProductsPage /> },
          { path: "/lending/apply/:productId", element: <LoanApplyPage /> },
          { path: paths.lendingApplications, element: <LoanApplicationsPage /> },
          { path: "/lending/loans/:loanId", element: <LoanDetailPage /> },
          { path: paths.traceability, element: <LotsListPage /> },
          { path: paths.lotNew, element: <LotCreatePage /> },
          { path: "/traceability/:lotId", element: <LotDetailPage /> },
          { path: paths.insurance, element: <PoliciesListPage /> },
          { path: paths.insuranceBuy, element: <PolicyBuyPage /> },
          { path: "/insurance/:policyId", element: <PolicyDetailPage /> },
          { path: paths.adminUsers, element: <AdminUsersPage /> },
          { path: "/admin/users/:userId", element: <AdminUserDetailPage /> },
          { path: paths.adminAudit, element: <AdminAuditPage /> },
          { path: paths.adminDisputes, element: <AdminDisputesPage /> },
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]);
