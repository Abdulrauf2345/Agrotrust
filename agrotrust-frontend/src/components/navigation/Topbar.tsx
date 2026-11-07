import { LogOut, User as UserIcon } from "lucide-react";
import { useAuth } from "@/lib/auth/AuthContext";
import { Button } from "@/components/ui/Button";

export function Topbar() {
  const { user, logout } = useAuth();

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-surface px-4">
      <div />
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-sm text-foreground">
          <UserIcon size={16} />
          {user?.full_name ?? "..."}
        </div>
        <Button variant="ghost" size="sm" onClick={logout}>
          <LogOut size={16} />
          Sign out
        </Button>
      </div>
    </header>
  );
}
