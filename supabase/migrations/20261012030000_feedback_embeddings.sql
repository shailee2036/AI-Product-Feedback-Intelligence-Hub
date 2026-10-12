-- Normalized feedback embeddings. One vector space per provider, model, and pipeline version.
-- pgvector lives in the extensions schema, matching Supabase.

create schema if not exists extensions;

do $body$
begin
  if not exists (select 1 from pg_extension where extname = 'vector') then
    execute 'create extension vector with schema extensions';
  end if;
end
$body$;

grant usage on schema extensions to authenticated;

alter table public.feedback_items
  add column content_hash text,
  add column detected_language text,
  add column redaction_count integer not null default 0;

alter table public.feedback_items add constraint feedback_items_content_hash_check
  check (content_hash is null or content_hash ~ '^[0-9a-f]{64}$');
alter table public.feedback_items add constraint feedback_items_redaction_count_check
  check (redaction_count >= 0);

create table public.embedding_runs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  status text not null check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
  provider text not null,
  model text not null,
  model_version text not null,
  dimensions integer not null check (dimensions = 384),
  embedded_count integer not null default 0 check (embedded_count >= 0),
  skipped_count integer not null default 0 check (skipped_count >= 0),
  unchanged_count integer not null default 0 check (unchanged_count >= 0),
  redaction_count integer not null default 0 check (redaction_count >= 0),
  error_message text,
  created_by uuid references auth.users (id) on delete set null,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now()
);

create unique index embedding_runs_one_active
  on public.embedding_runs (product_id)
  where status in ('queued', 'running');

create index embedding_runs_product_created_idx
  on public.embedding_runs (product_id, created_at desc);

create table public.feedback_embeddings (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  feedback_item_id uuid not null references public.feedback_items (id) on delete cascade,
  embedding_run_id uuid not null references public.embedding_runs (id) on delete cascade,
  provider text not null,
  model text not null,
  model_version text not null,
  dimensions integer not null check (dimensions = 384),
  embedding extensions.vector(384) not null,
  content_hash text not null check (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  unique (feedback_item_id, provider, model, model_version)
);

create index feedback_embeddings_product_idx on public.feedback_embeddings (product_id);

revoke all on public.embedding_runs, public.feedback_embeddings from anon, authenticated;
grant select, insert, update on public.embedding_runs, public.feedback_embeddings to authenticated;

alter table public.embedding_runs enable row level security;
alter table public.feedback_embeddings enable row level security;

create policy embedding_runs_tenant_all on public.embedding_runs
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));

create policy feedback_embeddings_tenant_all on public.feedback_embeddings
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));
