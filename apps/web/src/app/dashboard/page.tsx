import { redirect } from "next/navigation";

import { signOut } from "@/app/login/actions";
import { getVerifiedUserId } from "@/lib/supabase/server";

export default async function DashboardPage() {
  const userId = await getVerifiedUserId();
  if (!userId) redirect("/login?next=/dashboard");

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-6 py-12">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <form action={signOut}>
          <button type="submit" className="text-sm text-zinc-600 hover:underline dark:text-zinc-400">
            Sign out
          </button>
        </form>
      </header>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">You are signed in.</p>
    </main>
  );
}
