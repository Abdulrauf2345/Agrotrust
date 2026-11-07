import { Check, MapPin } from "lucide-react";
import type { DeliveryEvent } from "@/types/api";
import { formatDateTime } from "@/lib/formatting/date";

const EVENT_LABEL: Record<string, string> = {
  ASSIGNED: "Assigned to driver",
  PICKED_UP: "Picked up",
  IN_TRANSIT: "In transit",
  DELIVERED: "Delivered",
  CONFIRMED: "Confirmed by buyer",
  FAILED: "Delivery failed",
};

// Renders the actual delivery_events log, not a fixed happy-path strip like
// OrderTimeline. A shipment's events are a real append-only history with
// timestamps and, at pickup/delivery only, coordinates (milestone-only
// capture, see the backend's logistics service docstring), so showing them
// as a vertical log is more honest than compressing them into fixed steps.
export function ShipmentTrackTimeline({ events }: { events: DeliveryEvent[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-muted">No milestones recorded yet.</p>;
  }

  return (
    <ol className="flex flex-col gap-3">
      {events.map((event) => (
        <li key={event.id} className="flex gap-3">
          <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-primary bg-primary text-primary-foreground">
            <Check size={14} />
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-foreground">{EVENT_LABEL[event.event_type] ?? event.event_type}</p>
            <p className="text-xs text-muted">{formatDateTime(event.at)}</p>
            {event.lat !== null && event.lon !== null && (
              <p className="mt-0.5 flex items-center gap-1 text-xs text-muted">
                <MapPin size={12} />
                {event.lat.toFixed(4)}, {event.lon.toFixed(4)}
              </p>
            )}
            {event.note && <p className="mt-0.5 text-xs text-danger">{event.note}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
