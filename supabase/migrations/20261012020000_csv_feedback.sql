-- Customer-feedback CSV rows live beside GitHub issues on the same product.
-- A CSV upload is rejected unless that product already exists.

alter table public.imports drop constraint imports_source_check;
alter table public.imports add constraint imports_source_check
  check (source in ('github_issues', 'csv'));

alter table public.imports drop constraint imports_issue_limit_check;
alter table public.imports add constraint imports_issue_limit_check
  check (issue_limit between 1 and 10000);

alter table public.feedback_items drop constraint feedback_items_source_check;
alter table public.feedback_items add constraint feedback_items_source_check
  check (source in ('github_issue', 'csv'));

alter table public.feedback_items alter column github_number drop not null;
alter table public.feedback_items drop constraint feedback_items_github_number_check;
alter table public.feedback_items add constraint feedback_items_github_number_check
  check (github_number is null or github_number > 0);

alter table public.feedback_items alter column state drop not null;
alter table public.feedback_items drop constraint feedback_items_state_check;
alter table public.feedback_items add constraint feedback_items_state_check
  check (state is null or state in ('open', 'closed'));

alter table public.feedback_items alter column html_url drop not null;
alter table public.feedback_items drop constraint feedback_items_html_url_check;
alter table public.feedback_items add constraint feedback_items_html_url_check
  check (html_url is null or html_url like 'https://github.com/%');

alter table public.feedback_items add constraint feedback_items_source_shape check (
  (
    source = 'github_issue'
    and github_number is not null
    and state is not null
    and html_url is not null
  )
  or (source = 'csv' and github_number is null and html_url is null)
);

alter table public.feedback_items
  add column channel text,
  add column customer_segment text,
  add column product_area text,
  add column rating smallint,
  add column severity text,
  add column language text,
  add column is_synthetic boolean not null default false;

alter table public.feedback_items add constraint feedback_items_rating_check
  check (rating is null or rating between 1 and 5);
alter table public.feedback_items add constraint feedback_items_severity_check
  check (severity is null or severity in ('low', 'medium', 'high', 'critical'));
