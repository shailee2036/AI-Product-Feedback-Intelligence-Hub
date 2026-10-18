import { getMe } from "@/lib/api/client";

import { AppShell } from "@/components/app-shell";

import { requireToken } from "./load";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const token = await requireToken();
  let workspace = "Workspace";
  let email: string | null = null;
  try {
    const me = await getMe(token);
    workspace = me.workspace.name;
    email = me.email;
  } catch {
    workspace = "Workspace";
  }

  return (
    <AppShell workspace={workspace} email={email}>
      {children}
    </AppShell>
  );
}
