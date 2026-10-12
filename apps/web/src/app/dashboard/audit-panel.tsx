import type { AuditReport } from "@/lib/api/types";

export function AuditPanel({ report }: { report: AuditReport }) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-zinc-200 p-6 dark:border-zinc-800">
      <div>
        <h2 className="text-lg font-semibold">Activity</h2>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Recent workspace actions. Entries stay in the record and cannot be edited.
        </p>
      </div>
      {report.events.length === 0 ? (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">No activity yet.</p>
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
    </section>
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
