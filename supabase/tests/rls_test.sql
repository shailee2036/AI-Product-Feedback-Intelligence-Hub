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
end
$$;

\echo 'RLS tests passed'
rollback;
