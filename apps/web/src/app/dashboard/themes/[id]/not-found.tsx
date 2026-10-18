import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function ThemeNotFound() {
  return (
    <section className="rounded-2xl border border-border bg-card p-6">
      <h2 className="text-lg font-semibold">Theme not found</h2>
      <p className="mt-1 text-sm text-muted">It may have been merged, split, or not created yet.</p>
      <Button asChild className="mt-4" variant="secondary">
        <Link href="/dashboard/themes">Back to themes</Link>
      </Button>
    </section>
  );
}
