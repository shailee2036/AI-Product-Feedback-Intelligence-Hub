-- Switch the embedding index to Gemini's 768-dimension vectors.
-- The previous 384-dimension runs stored no vectors.

delete from public.feedback_embeddings;
delete from public.embedding_runs;

do $body$
declare
  drop_sql text;
begin
  for drop_sql in
    select format('alter table %s drop constraint %I', con.conrelid::regclass, con.conname)
    from pg_constraint con
    where con.conrelid in (
      'public.embedding_runs'::regclass,
      'public.feedback_embeddings'::regclass
    )
      and pg_get_constraintdef(con.oid) like '%dimensions = 384%'
  loop
    execute drop_sql;
  end loop;
end
$body$;

alter table public.embedding_runs
  add constraint embedding_runs_dimensions_check check (dimensions = 768);

alter table public.feedback_embeddings drop column embedding;
alter table public.feedback_embeddings
  add column embedding extensions.vector(768) not null;

alter table public.feedback_embeddings
  add constraint feedback_embeddings_dimensions_check check (dimensions = 768);
