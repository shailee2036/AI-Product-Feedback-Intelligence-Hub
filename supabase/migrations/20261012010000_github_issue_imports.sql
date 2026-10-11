-- GitHub issue imports for the registered product.
-- Issues are upserted by GitHub node id, so a later import updates the same rows.

create table public.imports (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  repository_id uuid not null references public.github_repositories (id) on delete cascade,
  source text not null check (source in ('github_issues')),
  status text not null check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
  issue_limit integer not null check (issue_limit between 1 and 500),
  imported_count integer not null default 0 check (imported_count >= 0),
  skipped_count integer not null default 0 check (skipped_count >= 0),
  not_modified boolean not null default false,
  error_message text,
  idempotency_key text,
  created_by uuid references auth.users (id) on delete set null,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  constraint imports_idempotency_key unique (tenant_id, idempotency_key)
);

create unique index imports_one_active_per_product
  on public.imports (product_id)
  where status in ('queued', 'running');

create index imports_product_created_idx on public.imports (product_id, created_at desc);

create table public.import_checkpoints (
  import_id uuid primary key references public.imports (id) on delete cascade,
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  page integer not null default 0 check (page >= 0),
  etag text,
  last_issue_updated_at timestamptz,
  updated_at timestamptz not null default now()
);

create table public.feedback_items (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  product_id uuid not null references public.products (id) on delete cascade,
  import_id uuid not null references public.imports (id) on delete cascade,
  source text not null check (source in ('github_issue')),
  external_id text not null check (char_length(external_id) between 1 and 200),
  github_number integer not null check (github_number > 0),
  title text not null check (char_length(title) between 1 and 300),
  body text not null default '',
  body_normalized text not null default '',
  state text not null check (state in ('open', 'closed')),
  html_url text not null check (html_url like 'https://github.com/%'),
  labels text[] not null default '{}',
  comment_count integer not null default 0 check (comment_count >= 0),
  reactions_total integer not null default 0 check (reactions_total >= 0),
  author_hash text,
  source_created_at timestamptz not null,
  source_updated_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (product_id, source, external_id)
);

create index feedback_items_product_updated_idx
  on public.feedback_items (product_id, source_updated_at desc);

revoke all on public.imports, public.import_checkpoints, public.feedback_items
  from anon, authenticated;

grant select, insert, update on public.imports, public.import_checkpoints, public.feedback_items
  to authenticated;

alter table public.imports enable row level security;
alter table public.import_checkpoints enable row level security;
alter table public.feedback_items enable row level security;

create policy imports_tenant_all on public.imports
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));

create policy import_checkpoints_tenant_all on public.import_checkpoints
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));

create policy feedback_items_tenant_all on public.feedback_items
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));
