-- Short names for candidate themes. A later naming run fills blank names only.
-- A name marked as edited stays in place. Finding themes again deletes these rows.

alter table public.candidate_clusters
  add column name text,
  add column summary text,
  add column name_edited boolean not null default false,
  add column name_provider text,
  add column name_model text,
  add constraint candidate_clusters_name_len
    check (name is null or char_length(name) between 1 and 80),
  add constraint candidate_clusters_summary_len
    check (summary is null or char_length(summary) between 1 and 400);

grant update (name, summary, name_provider, name_model)
  on public.candidate_clusters to authenticated;
