import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/lib/auth/AuthContext";
import type { Role } from "@/types/api";
import { paths } from "@/routes/paths";

// UI-level gate only, same caveat as permissions.ts: the backend re-checks
// every request, this just avoids flashing a page the user cannot act on.
export function RoleRoute({ allow }: { allow: Role[] }) {
  const { user } = useAuth();
  const hasAccess = user?.roles.some((r) => allow.includes(r)) ?? false;

  if (!hasAccess) {
    return <Navigate to={paths.dashboard} replace />;
  }

  return <Outlet />;
}
