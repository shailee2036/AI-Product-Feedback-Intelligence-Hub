-- A saved suggestion stays in the workspace. It is not posted to GitHub.

create table public.issue_suggestions (
  cluster_id uuid primary key references public.candidate_clusters (id) on delete cascade,
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  feedback_item_id uuid not null,
  comment text not null check (char_length(comment) between 1 and 2000),
  labels jsonb not null check (jsonb_typeof(labels) = 'array'),
  created_at timestamptz not null default now()
);

revoke all on public.issue_suggestions from anon, authenticated;
grant select, insert, update, delete on public.issue_suggestions to authenticated;

alter table public.issue_suggestions enable row level security;

create policy issue_suggestions_tenant_all on public.issue_suggestions
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));
