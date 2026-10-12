-- Review state for candidate themes. Approved themes survive the next clustering run.

alter table public.candidate_clusters
  add column status text not null default 'open',
  add constraint candidate_clusters_status
    check (status in ('open', 'approved', 'dismissed'));

grant update (name_edited, status) on public.candidate_clusters to authenticated;
