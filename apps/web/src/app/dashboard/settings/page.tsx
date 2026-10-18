import type { Metadata } from "next";

import { Card, CardDescription, CardTitle } from "@/components/ui/card";

import { AuditPanel } from "../audit-panel";
import { EmptyProduct } from "../empty-product";
import { loadWorkspace } from "../load";
import { WorkspaceError } from "../workspace-error";

export const metadata: Metadata = { title: "Settings · Feedback Intelligence Hub" };

export default async function SettingsPage() {
  const data = await loadWorkspace();
  if ("error" in data) return <WorkspaceError message={data.error} />;
  if (!data.product) {
    return (
      <div className="flex flex-col gap-8">
        <EmptyProduct />
        <AuditPanel report={data.audit} />
      </div>
    );
  }

  const repo = data.product.repository;
  const registered = new Date(data.product.created_at).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted">Repository details and the workspace activity log.</p>
      </div>
      <Card>
        <p className="text-sm font-medium text-accent">Registered product</p>
        <CardTitle className="mt-1">{data.product.name}</CardTitle>
        <a
          href={repo.html_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-accent hover:underline"
        >
          {repo.full_name}
        </a>
        <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-muted">License</dt>
            <dd className="font-medium">{repo.license_spdx}</dd>
          </div>
          <div>
            <dt className="text-muted">Default branch</dt>
            <dd className="font-medium">{repo.default_branch}</dd>
          </div>
          <div>
            <dt className="text-muted">Registered</dt>
            <dd className="font-medium">{registered}</dd>
          </div>
        </dl>
        <CardDescription className="mt-4">
          Version 1 registers one public organization repository. GitHub writes stay off.
        </CardDescription>
      </Card>
      <AuditPanel report={data.audit} />
    </div>
  );
}
