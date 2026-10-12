-- Each write or edit of a brief keeps the earlier text.

alter table public.product_briefs
  add column version_number integer not null default 1,
  add column source text not null default 'generated',
  add constraint product_briefs_source check (source in ('generated', 'edited')),
  alter column provider drop not null,
  alter column model drop not null;

create table public.product_brief_versions (
  id uuid primary key default gen_random_uuid(),
  cluster_id uuid not null references public.candidate_clusters (id) on delete cascade,
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  version_number integer not null check (version_number >= 1),
  source text not null check (source in ('generated', 'edited')),
  problem text not null check (char_length(problem) between 1 and 400),
  impact text not null check (char_length(impact) between 1 and 400),
  evidence_summary text not null check (char_length(evidence_summary) between 1 and 600),
  non_goals text not null check (char_length(non_goals) between 1 and 400),
  acceptance_criteria text not null check (char_length(acceptance_criteria) between 1 and 600),
  open_questions text not null check (char_length(open_questions) between 1 and 400),
  evidence_ids jsonb not null check (
    jsonb_typeof(evidence_ids) = 'array' and jsonb_array_length(evidence_ids) >= 1
  ),
  provider text,
  model text,
  created_at timestamptz not null default now(),
  unique (cluster_id, version_number)
);

revoke all on public.product_brief_versions from anon, authenticated;
grant select, insert, delete on public.product_brief_versions to authenticated;

alter table public.product_brief_versions enable row level security;

create policy product_brief_versions_tenant_all on public.product_brief_versions
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));

insert into public.product_brief_versions (
  cluster_id, tenant_id, product_id, version_number, source, problem, impact,
  evidence_summary, non_goals, acceptance_criteria, open_questions, evidence_ids,
  provider, model, created_at
)
select
  cluster_id, tenant_id, product_id, version_number, source, problem, impact,
  evidence_summary, non_goals, acceptance_criteria, open_questions, evidence_ids,
  provider, model, created_at
from public.product_briefs;
