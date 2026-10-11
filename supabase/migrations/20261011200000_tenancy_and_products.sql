-- Tenancy, product registration, and audit trail.
-- Every tenant-owned table carries tenant_id and is protected by row-level security.
-- v1 rules: one workspace per user, one product per workspace, one repository per product.

create schema if not exists app;
revoke all on schema app from public;
grant usage on schema app to authenticated;

-- Workspaces -----------------------------------------------------------------

create table public.tenants (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(name) between 1 and 120),
  created_at timestamptz not null default now()
);

create table public.memberships (
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  role text not null check (role in ('owner', 'member')),
  created_at timestamptz not null default now(),
  primary key (tenant_id, user_id)
);

create unique index memberships_one_workspace_per_user on public.memberships (user_id);

create function app.current_tenant_ids()
returns setof uuid
language sql
stable
security definer
set search_path = ''
as $$
  select m.tenant_id from public.memberships m where m.user_id = auth.uid()
$$;

revoke all on function app.current_tenant_ids() from public;
grant execute on function app.current_tenant_ids() to authenticated;

-- Creates the caller's workspace on first use; returns the existing one afterwards.
create function app.ensure_workspace(p_name text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user uuid := auth.uid();
  v_tenant uuid;
begin
  if v_user is null then
    raise exception 'authentication required' using errcode = '28000';
  end if;

  select tenant_id into v_tenant from public.memberships where user_id = v_user;
  if v_tenant is not null then
    return v_tenant;
  end if;

  insert into public.tenants (name) values (left(coalesce(nullif(trim(p_name), ''), 'My workspace'), 120))
  returning id into v_tenant;

  insert into public.memberships (tenant_id, user_id, role)
  values (v_tenant, v_user, 'owner')
  on conflict (user_id) do nothing;

  if not found then
    delete from public.tenants where id = v_tenant;
    select tenant_id into v_tenant from public.memberships where user_id = v_user;
  end if;

  return v_tenant;
end;
$$;

revoke all on function app.ensure_workspace(text) from public;
grant execute on function app.ensure_workspace(text) to authenticated;

-- Products and repositories ---------------------------------------------------

create table public.products (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null unique references public.tenants (id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.github_repositories (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  product_id uuid not null unique references public.products (id) on delete cascade,
  github_node_id text not null,
  owner text not null,
  name text not null,
  full_name text not null,
  html_url text not null check (html_url like 'https://github.com/%'),
  default_branch text not null,
  license_spdx text not null,
  created_at timestamptz not null default now(),
  unique (tenant_id, github_node_id)
);

create index github_repositories_tenant_idx on public.github_repositories (tenant_id);

create table public.repository_license_checks (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  repository_id uuid not null references public.github_repositories (id) on delete cascade,
  eligible boolean not null,
  reasons text[] not null default '{}',
  license_spdx text,
  checked_at timestamptz not null default now()
);

create index repository_license_checks_repo_idx
  on public.repository_license_checks (repository_id, checked_at desc);

-- Audit trail (append-only) ---------------------------------------------------

create table public.audit_events (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  actor_id uuid references auth.users (id) on delete set null,
  action text not null check (action ~ '^[a-z_]+(\.[a-z_]+)+$'),
  target_type text,
  target_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index audit_events_tenant_created_idx on public.audit_events (tenant_id, created_at desc);

-- Privileges ------------------------------------------------------------------

revoke all on public.tenants, public.memberships, public.products, public.github_repositories,
  public.repository_license_checks, public.audit_events from anon, authenticated;

grant select on public.tenants, public.memberships to authenticated;
grant select, insert, update, delete on public.products, public.github_repositories to authenticated;
grant select, insert on public.repository_license_checks, public.audit_events to authenticated;

-- Row-level security ----------------------------------------------------------

alter table public.tenants enable row level security;
alter table public.memberships enable row level security;
alter table public.products enable row level security;
alter table public.github_repositories enable row level security;
alter table public.repository_license_checks enable row level security;
alter table public.audit_events enable row level security;

create policy tenants_member_read on public.tenants
  for select to authenticated
  using (id in (select app.current_tenant_ids()));

create policy memberships_self_read on public.memberships
  for select to authenticated
  using (user_id = (select auth.uid()));

create policy products_tenant_all on public.products
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));

create policy github_repositories_tenant_all on public.github_repositories
  for all to authenticated
  using (tenant_id in (select app.current_tenant_ids()))
  with check (tenant_id in (select app.current_tenant_ids()));

create policy license_checks_tenant_read on public.repository_license_checks
  for select to authenticated
  using (tenant_id in (select app.current_tenant_ids()));

create policy license_checks_tenant_insert on public.repository_license_checks
  for insert to authenticated
  with check (tenant_id in (select app.current_tenant_ids()));

create policy audit_events_tenant_read on public.audit_events
  for select to authenticated
  using (tenant_id in (select app.current_tenant_ids()));

create policy audit_events_tenant_insert on public.audit_events
  for insert to authenticated
  with check (
    tenant_id in (select app.current_tenant_ids())
    and actor_id = (select auth.uid())
  );
