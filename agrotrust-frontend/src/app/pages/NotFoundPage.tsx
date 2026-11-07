import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { paths } from "@/routes/paths";

export function NotFoundPage() {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-3 text-center">
      <h1 className="text-3xl font-bold text-foreground">404</h1>
      <p className="text-muted">That page does not exist.</p>
      <Link to={paths.dashboard}>
        <Button>Back to dashboard</Button>
      </Link>
    </div>
  );
}
