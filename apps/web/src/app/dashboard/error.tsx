"use client";

import { Button } from "@/components/ui/button";

export default function DashboardError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section role="alert" className="rounded-2xl border border-border bg-card p-6">
      <h2 className="text-lg font-semibold">This page could not be shown.</h2>
      <p className="mt-1 text-sm text-muted">Try again. Your workspace data was not changed.</p>
      <Button className="mt-4" type="button" onClick={reset}>
        Try again
      </Button>
    </section>
  );
}
