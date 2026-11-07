import { useNotifications, useMarkRead } from "../hooks";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatRelativeTime } from "@/lib/formatting/date";

export function NotificationsPage() {
  const { data, isLoading } = useNotifications();
  const markRead = useMarkRead();

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold text-foreground">Notifications</h1>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : !data?.length ? (
        <EmptyState title="You're all caught up" description="New notifications will show up here." />
      ) : (
        <div className="flex flex-col gap-2">
          {data.map((n) => (
            <Card key={n.id} className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-medium text-foreground">{n.title}</p>
                  {!n.read_at && <Badge tone="primary">New</Badge>}
                </div>
                <p className="text-sm text-muted">{n.body}</p>
                <p className="mt-1 text-xs text-muted">{formatRelativeTime(n.created_at)}</p>
              </div>
              {!n.read_at && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => markRead.mutate(n.id)}
                  loading={markRead.isPending && markRead.variables === n.id}
                >
                  Mark read
                </Button>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
