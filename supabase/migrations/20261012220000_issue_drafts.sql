-- A saved new-issue draft stays in the workspace. It is not created on GitHub.

create table public.issue_drafts (
  cluster_id uuid primary key references public.candidate_clusters (id) on delete cascade,
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  title text not null check (char_length(title) between 1 and 120),
  body text not null check (char_length(body) between 1 and 2000),
  labels jsonb not null check (jsonb_typeof(labels) = 'array'),
  created_at timestamptz not null default now()
);

revoke all on public.issue_drafts from anon, authenticated;
grant select, insert, update, delete on public.issue_drafts to authenticated;

alter table public.issue_drafts enable row level security;

create policy issue_drafts_tenant_all on public.issue_drafts
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));
