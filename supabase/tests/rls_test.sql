-- Row-level security assertions. Run with: psql -v ON_ERROR_STOP=1 -f rls_test.sql
-- Everything runs inside a transaction that is rolled back.

begin;

insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-00000000000a', 'alice@example.com'),
  ('00000000-0000-0000-0000-00000000000b', 'bob@example.com');

create function pg_temp.act_as(p_user uuid) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims', json_build_object('sub', p_user, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';
end;
$$;

-- Alice and Bob each get exactly one workspace, and calling again is idempotent.
select pg_temp.act_as('00000000-0000-0000-0000-00000000000a');
select app.ensure_workspace('Alice Co') as alice_tenant \gset
do $$
begin
  if app.ensure_workspace('Renamed') <> (select tenant_id from public.memberships) then
    raise exception 'ensure_workspace is not idempotent';
  end if;
end
$$;

insert into public.products (tenant_id, name, created_by)
values (:'alice_tenant', 'appwrite', '00000000-0000-0000-0000-00000000000a');

insert into public.github_repositories (
  tenant_id, product_id, github_node_id, owner, name, full_name, html_url, default_branch, license_spdx
)
select :'alice_tenant', id, 'node-appwrite', 'appwrite', 'appwrite', 'appwrite/appwrite',
       'https://github.com/appwrite/appwrite', 'main', 'BSD-3-Clause'
from public.products
returning id as alice_repo \gset

insert into public.imports (tenant_id, product_id, repository_id, source, status, issue_limit, created_by)
select :'alice_tenant', id, :'alice_repo', 'github_issues', 'succeeded', 100,
       '00000000-0000-0000-0000-00000000000a'
from public.products
returning id as alice_import \gset

insert into public.feedback_items (
  tenant_id, product_id, import_id, source, external_id, github_number, title, state, html_url,
  source_created_at, source_updated_at
)
select :'alice_tenant', id, :'alice_import', 'github_issue', 'issue-node-1', 1, 'Login fails',
       'open', 'https://github.com/appwrite/appwrite/issues/1', now(), now()
from public.products;

insert into public.feedback_items (
  tenant_id, product_id, import_id, source, external_id, github_number, title, state, html_url,
  source_created_at, source_updated_at
)
select :'alice_tenant', id, :'alice_import', 'github_issue', 'issue-node-2', 2, 'Login fails again',
       'open', 'https://github.com/appwrite/appwrite/issues/2', now(), now()
from public.products;

insert into public.duplicate_edges (
  tenant_id, product_id, left_item_id, right_item_id, kind, score, provider, model, model_version
)
select :'alice_tenant', p.id, least(a.id, b.id), greatest(a.id, b.id),
       'exact', 1, 'gemini', 'gemini-embedding-001', '1'
from public.products p
join public.feedback_items a on a.external_id = 'issue-node-1'
join public.feedback_items b on b.external_id = 'issue-node-2';

insert into public.dedupe_runs (
  tenant_id, product_id, exact_count, semantic_count, group_count, threshold, neighbor_count,
  provider, model, model_version
)
select :'alice_tenant', id, 1, 0, 1, 0.86, 2, 'gemini', 'gemini-embedding-001', '1'
from public.products;

reset role;
select pg_temp.act_as('00000000-0000-0000-0000-00000000000b');
select app.ensure_workspace('Bob Co') as bob_tenant \gset

do $$
begin
  if (select count(*) from public.tenants) <> 1 then
    raise exception 'Bob can see another tenant';
  end if;
  if exists (select 1 from public.products) then
    raise exception 'Bob can read Alice''s product';
  end if;
  if exists (select 1 from public.imports) then
    raise exception 'Bob can read Alice''s imports';
  end if;
  if exists (select 1 from public.feedback_items) then
    raise exception 'Bob can read Alice''s imported issues';
  end if;
  if exists (select 1 from public.duplicate_edges) then
    raise exception 'Bob can read Alice''s duplicate edges';
  end if;
  if exists (select 1 from public.dedupe_runs) then
    raise exception 'Bob can read Alice''s dedupe runs';
  end if;
  if exists (select 1 from public.memberships where user_id <> auth.uid()) then
    raise exception 'Bob can read another user''s membership';
  end if;
end
$$;

-- Bob cannot write into, update, or delete from Alice's tenant.
select set_config('test.alice_tenant', :'alice_tenant', true);
do $$
declare
  v_blocked boolean := false;
begin
  begin
    insert into public.products (tenant_id, name)
    values (current_setting('test.alice_tenant')::uuid, 'hijack');
  exception when insufficient_privilege then
    v_blocked := true;
  end;
  if not v_blocked then
    raise exception 'Bob inserted a product into Alice''s tenant';
  end if;

  update public.products set name = 'pwned' where tenant_id = current_setting('test.alice_tenant')::uuid;
  delete from public.products where tenant_id = current_setting('test.alice_tenant')::uuid;
end
$$;

-- Audit events are append-only and must be attributed to the caller.
do $$
declare
  v_blocked boolean := false;
begin
  insert into public.audit_events (tenant_id, actor_id, action)
  values ((select tenant_id from public.memberships), auth.uid(), 'workspace.created');

  begin
    insert into public.audit_events (tenant_id, actor_id, action)
    values ((select tenant_id from public.memberships), '00000000-0000-0000-0000-00000000000a', 'product.registered');
  exception when insufficient_privilege then
    v_blocked := true;
  end;
  if not v_blocked then
    raise exception 'Audit event accepted a spoofed actor';
  end if;

  v_blocked := false;
  begin
    update public.audit_events set action = 'tampered.event';
  exception when insufficient_privilege then
    v_blocked := true;
  end;
  if not v_blocked then
    raise exception 'Audit events are mutable';
  end if;
end
$$;

-- Anonymous callers see nothing and cannot create workspaces.
reset role;
set local role anon;
do $$
declare
  v_blocked boolean := false;
begin
  begin
    perform 1 from public.tenants;
  exception when insufficient_privilege then
    v_blocked := true;
  end;
  if not v_blocked then
    raise exception 'anon can read tenants';
  end if;
end
$$;

-- Alice's product survived Bob's update and delete attempts.
reset role;
select pg_temp.act_as('00000000-0000-0000-0000-00000000000a');
do $$
begin
  if (select name from public.products) is distinct from 'appwrite' then
    raise exception 'Alice''s product was modified by another tenant';
  end if;
  if (select count(*) from public.duplicate_edges) <> 1 then
    raise exception 'Alice''s duplicate edge disappeared';
  end if;
end
$$;

\echo 'RLS tests passed'
rollback;
