export function WorkspaceError({ message }: { message: string }) {
  return (
    <section
      role="alert"
      className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
    >
      <p className="font-medium">Could not load your workspace.</p>
      <p className="mt-1">{message}</p>
    </section>
  );
}
