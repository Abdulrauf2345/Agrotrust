import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/lib/auth/AuthContext";
import { Spinner } from "@/components/ui/Spinner";
import { paths } from "@/routes/paths";

export function ProtectedRoute() {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner size={32} />
      </div>
    );
  }

  if (status === "unauthenticated") {
    return <Navigate to={paths.login} replace />;
  }

  return <Outlet />;
}
