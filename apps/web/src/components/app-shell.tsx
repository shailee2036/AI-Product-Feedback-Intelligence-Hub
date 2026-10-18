"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  FileStack,
  GitBranch,
  LayoutDashboard,
  Settings,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { signOut } from "@/app/login/actions";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/dashboard/imports", label: "Imports", icon: GitBranch },
  { href: "/dashboard/analysis", label: "Analysis", icon: BarChart3 },
  { href: "/dashboard/themes", label: "Themes", icon: FileStack },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

export function AppShell({
  workspace,
  email,
  children,
}: {
  workspace: string;
  email: string | null;
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[16rem_1fr]">
      <aside className="bg-sidebar px-4 py-4 text-sidebar-foreground lg:px-5 lg:py-6">
        <Link href="/dashboard" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-teal-400/20">
            <Activity className="h-4 w-4 text-teal-200" />
          </span>
          Feedback Hub
        </Link>
        <nav className="mt-6 flex gap-1 overflow-x-auto lg:flex-col">
          {NAV.map((item) => {
            const active =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname === item.href || pathname.startsWith(`${item.href}/`);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap",
                  active
                    ? "bg-teal-300/20 text-white"
                    : "text-teal-100/70 hover:bg-white/10 hover:text-white",
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-col">
        <header className="flex items-center justify-between gap-4 border-b border-border bg-card/70 px-6 py-3 backdrop-blur">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{workspace}</p>
            {email ? <p className="truncate text-xs text-muted">{email}</p> : null}
          </div>
          <form action={signOut}>
            <Button type="submit" variant="ghost" size="sm">
              Sign out
            </Button>
          </form>
        </header>
        <div className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</div>
      </div>
    </div>
  );
}
