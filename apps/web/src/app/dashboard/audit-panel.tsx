import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import type { AuditReport } from "@/lib/api/types";

export function AuditPanel({ report }: { report: AuditReport }) {
  return (
    <Card className="flex flex-col gap-3">
      <div>
        <CardTitle>Activity</CardTitle>
        <CardDescription>
          Recent workspace actions. Entries stay in the record and cannot be edited.
        </CardDescription>
      </div>
      {report.events.length === 0 ? (
        <p className="text-sm text-muted">No activity yet.</p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {report.events.map((event) => (
            <li key={event.id} className="flex items-baseline justify-between gap-4">
              <span>{event.summary}</span>
              <time className="shrink-0 text-xs text-zinc-500" dateTime={event.created_at}>
                {formatWhen(event.created_at)}
              </time>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function formatWhen(value: string): string {
  const moment = new Date(value);
  if (Number.isNaN(moment.getTime())) return value;
  return moment.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
