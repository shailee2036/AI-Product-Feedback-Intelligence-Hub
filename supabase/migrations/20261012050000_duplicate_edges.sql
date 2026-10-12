-- Derived duplicate links. Original feedback rows are never merged or deleted.
-- A new run replaces the edges and appends a dedupe_runs summary.

create table public.duplicate_edges (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  left_item_id uuid not null references public.feedback_items (id) on delete cascade,
  right_item_id uuid not null references public.feedback_items (id) on delete cascade,
  kind text not null check (kind in ('exact', 'semantic')),
  score double precision not null check (score >= 0 and score <= 1),
  provider text not null,
  model text not null,
  model_version text not null,
  created_at timestamptz not null default now(),
  unique (product_id, left_item_id, right_item_id),
  check (left_item_id < right_item_id)
);

create index duplicate_edges_product_idx on public.duplicate_edges (product_id);

create table public.dedupe_runs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  exact_count integer not null check (exact_count >= 0),
  semantic_count integer not null check (semantic_count >= 0),
  group_count integer not null check (group_count >= 0),
  threshold double precision not null check (threshold > 0 and threshold <= 1),
  neighbor_count integer not null check (neighbor_count >= 1),
  provider text not null,
  model text not null,
  model_version text not null,
  created_at timestamptz not null default now()
);

create index dedupe_runs_product_created_idx
  on public.dedupe_runs (product_id, created_at desc);

revoke all on public.duplicate_edges, public.dedupe_runs from anon, authenticated;
grant select, insert, delete on public.duplicate_edges to authenticated;
grant select, insert on public.dedupe_runs to authenticated;

alter table public.duplicate_edges enable row level security;
alter table public.dedupe_runs enable row level security;

create policy duplicate_edges_tenant_all on public.duplicate_edges
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));

create policy dedupe_runs_tenant_all on public.dedupe_runs
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));
