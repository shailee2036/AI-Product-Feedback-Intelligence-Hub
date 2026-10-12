-- One evidence-linked brief per theme. Deleting the theme deletes the brief.

create table public.product_briefs (
  cluster_id uuid primary key references public.candidate_clusters (id) on delete cascade,
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  problem text not null check (char_length(problem) between 1 and 400),
  impact text not null check (char_length(impact) between 1 and 400),
  evidence_summary text not null check (char_length(evidence_summary) between 1 and 600),
  non_goals text not null check (char_length(non_goals) between 1 and 400),
  acceptance_criteria text not null check (char_length(acceptance_criteria) between 1 and 600),
  open_questions text not null check (char_length(open_questions) between 1 and 400),
  evidence_ids jsonb not null check (
    jsonb_typeof(evidence_ids) = 'array' and jsonb_array_length(evidence_ids) >= 1
  ),
  provider text not null,
  model text not null,
  created_at timestamptz not null default now()
);

revoke all on public.product_briefs from anon, authenticated;
grant select, insert, update, delete on public.product_briefs to authenticated;

alter table public.product_briefs enable row level security;

create policy product_briefs_tenant_all on public.product_briefs
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));
