import { Outlet } from "react-router-dom";

export function AuthLayout() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm rounded border border-border bg-surface p-6 shadow-sm">
        <div className="mb-6 text-center text-xl font-bold text-primary">AgroTrust</div>
        <Outlet />
      </div>
    </div>
  );
}
