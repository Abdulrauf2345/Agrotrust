import { Link } from "react-router-dom";
import { Card } from "@/components/ui/Card";

export interface QuickLink {
  label: string;
  to: string;
  description: string;
}

export function QuickLinks({ links }: { links: QuickLink[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {links.map((link) => (
        <Link key={link.to} to={link.to}>
          <Card className="h-full transition-colors hover:border-primary">
            <p className="font-medium text-foreground">{link.label}</p>
            <p className="mt-1 text-sm text-muted">{link.description}</p>
          </Card>
        </Link>
      ))}
    </div>
  );
}
