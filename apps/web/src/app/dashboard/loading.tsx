export default function DashboardLoading() {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="h-28 animate-pulse rounded-2xl bg-zinc-200/70 dark:bg-zinc-800" />
      ))}
      <div className="h-72 animate-pulse rounded-2xl bg-zinc-200/70 md:col-span-3 dark:bg-zinc-800" />
    </div>
  );
}
