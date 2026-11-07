import { EmptyState } from "@/components/ui/EmptyState";

export function GenericDashboard() {
  return (
    <EmptyState
      title="No dashboard view for this role yet"
      description="This role's dashboard has not been built in this pass. The backend's analytics endpoints for this role work and can be wired up next."
    />
  );
}
