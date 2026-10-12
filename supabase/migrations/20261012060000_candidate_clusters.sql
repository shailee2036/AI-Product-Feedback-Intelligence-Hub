-- Candidate themes from the stored embeddings. Original feedback rows stay in place.
-- A new run replaces these clusters. Named, reviewed themes come later.

create table public.analysis_runs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  cluster_count integer not null check (cluster_count >= 0),
  member_count integer not null check (member_count >= 0),
  threshold double precision not null check (threshold > 0 and threshold <= 1),
  neighbor_count integer not null check (neighbor_count >= 1),
  minimum_size integer not null check (minimum_size >= 2),
  provider text not null,
  model text not null,
  model_version text not null,
  created_at timestamptz not null default now()
);

create index analysis_runs_product_created_idx
  on public.analysis_runs (product_id, created_at desc);

create table public.candidate_clusters (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  analysis_run_id uuid not null references public.analysis_runs (id) on delete cascade,
  created_at timestamptz not null default now()
);

create index candidate_clusters_run_idx on public.candidate_clusters (analysis_run_id);

create table public.candidate_cluster_members (
  cluster_id uuid not null references public.candidate_clusters (id) on delete cascade,
  feedback_item_id uuid not null references public.feedback_items (id) on delete cascade,
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  primary key (cluster_id, feedback_item_id)
);

create index candidate_cluster_members_item_idx
  on public.candidate_cluster_members (feedback_item_id);

revoke all on public.analysis_runs, public.candidate_clusters, public.candidate_cluster_members
  from anon, authenticated;
grant select, insert, delete on public.analysis_runs to authenticated;
grant select, insert, delete on public.candidate_clusters to authenticated;
grant select, insert, delete on public.candidate_cluster_members to authenticated;

alter table public.analysis_runs enable row level security;
alter table public.candidate_clusters enable row level security;
alter table public.candidate_cluster_members enable row level security;

create policy analysis_runs_tenant_all on public.analysis_runs
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));

create policy candidate_clusters_tenant_all on public.candidate_clusters
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));

create policy candidate_cluster_members_tenant_all on public.candidate_cluster_members
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));
