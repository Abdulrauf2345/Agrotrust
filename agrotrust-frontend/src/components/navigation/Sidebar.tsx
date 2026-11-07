import { NavLink } from "react-router-dom";
import { NAV_ITEMS } from "./navConfig";
import { useAuth } from "@/lib/auth/AuthContext";
import { cn } from "@/lib/utilities/cn";

export function Sidebar() {
  const { user } = useAuth();
  const roles = user?.roles ?? [];

  const items = NAV_ITEMS.filter((item) => !item.roles || item.roles.some((r) => roles.includes(r)));

  return (
    <nav className="flex w-56 shrink-0 flex-col gap-1 border-r border-border bg-surface p-3">
      <div className="mb-4 px-2 text-lg font-bold text-primary">AgroTrust</div>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2 rounded px-3 py-2 text-sm font-medium text-foreground hover:bg-background",
              isActive && "bg-primary/10 text-primary",
            )
          }
        >
          <item.icon size={18} />
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
