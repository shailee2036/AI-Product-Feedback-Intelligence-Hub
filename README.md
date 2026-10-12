# AI Product Feedback Intelligence Hub

Turns GitHub issues and uploaded customer feedback for a single open-source product into
evidence-backed product themes. Each theme is linked to an existing canonical GitHub issue;
a new issue is drafted only when no suitable one exists, and every GitHub write requires
explicit human confirmation.

The full blueprint lives in [PROJECT_PLAN.md](PROJECT_PLAN.md).

## Repository layout

| Path | Purpose |
| --- | --- |
| `apps/api` | FastAPI backend: product registration, eligibility, imports, analysis APIs |
| `apps/web` | Next.js frontend: Supabase sign-in, dashboard, repository registration |
| `supabase/migrations` | Postgres schema and row-level security policies (source of truth) |
| `supabase/tests` | SQL row-level security tests and a Supabase auth stub for plain Postgres |
| `seed-data` | Appwrite seed source and synthetic CSV fixture |
| `compose.yaml` | Local Postgres (pgvector) and Redis for integration tests |
| `.github/workflows` | CI, security, and delivery pipelines |

More workspaces (workers, `infra/helm`) are added as milestones land.

## Local development

### Backend

```bash
cd apps/api
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # then fill in the Supabase and GitHub values

ruff format --check . && ruff check . && mypy
pytest -m "not integration"
uvicorn feedback_hub.main:app --reload
```

### API chart

The chart in `deploy/charts/api` runs the API on CPU with requests, limits, and health probes. It does not contain credentials. Create a Secret named `feedback-hub-api` in the target namespace, then render the chart with an immutable image tag and check it against the Kubernetes 1.37 schema:

```bash
helm lint deploy/charts/api --set image.tag="$(git rev-parse HEAD)"
helm template feedback-hub-api deploy/charts/api --set image.tag="$(git rev-parse HEAD)" > rendered.yaml
kubeconform -strict -summary -kubernetes-version 1.37.0 rendered.yaml
```

`latest` is rejected. CI lints the chart and validates the rendered manifests. It does not install the chart to a cluster.

### Frontend

Requires Node.js 22 or newer and the backend running on `http://127.0.0.1:8000`.

```bash
cd apps/web
npm ci
cp .env.example .env.local   # Supabase URL + publishable key; API_URL; SITE_URL=http://localhost:3100

npm run lint && npm run typecheck && npm run test:coverage
npm run dev                  # http://localhost:3100
```

The browser only talks to Supabase Auth. Calls to the API happen in server components and
server actions, which forward the signed-in user's access token, so `API_URL` is never exposed
to the browser and the API needs no CORS configuration.

### Integration tests

```bash
docker compose up -d --wait          # from the repository root
export FEEDBACK_HUB_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54329/postgres
cd apps/api && pytest -m integration
```

The tests create a throwaway database, apply `supabase/tests/auth_stub.sql` plus every migration,
and drop it afterwards.

### Database migrations

Migrations in `supabase/migrations` are applied to the hosted project with the Supabase CLI:

```bash
npx supabase db push --db-url "$FEEDBACK_HUB_DATABASE_URL"
```

Never apply `supabase/tests/auth_stub.sql` to a real Supabase project.

### API endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/health/live`, `/health/ready` | none | Liveness and readiness (database check) |
| GET | `/metrics` | none (cluster-internal) | Prometheus metrics |
| POST | `/v1/repositories/eligibility` | none | Check whether a public repository is eligible |
| GET | `/v1/me` | user | Current user; creates the workspace on first call |
| GET | `/v1/audit` | user | Recent workspace actions; append-only |
| GET | `/v1/product` | user | The workspace's registered product |
| POST | `/v1/product/github` | user | Register the workspace product from an eligible repository |
| POST | `/v1/imports` | user | Import the registered repository's most recently updated issues |
| GET | `/v1/imports/current` | user | The latest import and its progress |
| POST | `/v1/imports/{import_id}/cancel` | user | Cancel a queued or running import |
| GET | `/v1/feedback` | user | Imported issues and CSV rows for the registered product |
| POST | `/v1/product/csv` | user | Upload a customer-feedback CSV for the registered product |
| POST | `/v1/feedback/embeddings` | user | Embed saved feedback with Gemini embedding-001 |
| GET | `/v1/feedback/embeddings/current` | user | Latest embedding run and how many vectors are stored |
| POST | `/v1/feedback/duplicates` | user | Rebuild exact and semantic duplicate links |
| GET | `/v1/feedback/duplicates` | user | Latest duplicate groups; original rows are unchanged |
| POST | `/v1/feedback/clusters` | user | Group embedded feedback into candidate themes |
| GET | `/v1/feedback/clusters` | user | Latest candidate themes; original rows are unchanged |
| POST | `/v1/feedback/clusters/names` | user | Name untitled themes from redacted titles |
| PATCH | `/v1/feedback/clusters/{cluster_id}` | user | Save a theme name and summary |
| POST | `/v1/feedback/clusters/{cluster_id}/decision` | user | Approve or dismiss a theme |
| POST | `/v1/feedback/clusters/{cluster_id}/merge` | user | Move a theme's rows into another theme |
| POST | `/v1/feedback/clusters/{cluster_id}/split` | user | Move selected rows into a new theme |
| POST | `/v1/feedback/clusters/{cluster_id}/brief` | user | Write an evidence-linked brief for an approved theme |
| PATCH | `/v1/feedback/clusters/{cluster_id}/brief` | user | Save an edited brief and keep earlier versions |
| POST | `/v1/feedback/clusters/{cluster_id}/suggestion` | user | Save a suggested comment and labels locally |
| POST | `/v1/feedback/clusters/{cluster_id}/issue-draft` | user | Preview a new issue draft and similar open issues |
| POST | `/v1/feedback/clusters/{cluster_id}/issue-draft/confirmation` | user | Save a confirmed new-issue draft locally |

Exact duplicates share a hash of the redacted text. Semantic duplicates are mutual nearest
neighbors with cosine similarity of at least 0.86. A starter set of labeled seed pairs is scored
with each run. The full 200-pair review is later manual labeling.

Candidate themes are mutual nearest neighbors with cosine similarity of at least 0.82 and at
least three rows. A starter set of seed themes is scored with each run. Naming sends up to six
redacted titles per theme to Groq in one request and stores a short name and summary. A name
already stored, including one marked as edited, stays in place. Approving a theme keeps it
when themes are found again. Open and dismissed themes are replaced. Merge moves every row
into another theme. Split moves the selected rows into a new theme. Each theme also has a
score that averages five factors from the stored rows: size (full at 10 rows), the share created
in the last 90 days, source mix (one source is 0.5 and two or more is 1), volume after duplicate
rows inside the theme are counted once, and completeness (a stored name plus the share of rows
with an embedding). The score is not asked of a model. An approved theme can get a product
brief from up to six redacted titles. The brief cites only rows in that theme, and writing it
again replaces the current text and keeps every earlier version. Each theme also recommends
one imported GitHub issue as the canonical issue. Open issues rank ahead of closed ones. The
score then averages semantic coverage (mean similarity to the other rows in the theme),
discussion (full at 10 comments), reactions (full at 10), and whether the issue was updated in
the last 90 days. Other open issues in the theme, and open issues outside it with similarity of
at least 0.86, are shown as possible duplicates. When a canonical issue exists, the theme also
drafts a comment from the brief and related CSV titles, plus labels from product areas. Saving
that draft keeps it in the workspace. Nothing is created, closed, or commented on GitHub.
A new issue draft is available only after the maintainer chooses "No suitable existing issue" on an
approved theme. The draft lists every open issue already in the theme, and any open issue outside
it with similarity of at least 0.86. Saving requires an explicit confirmation and keeps the title
and body in the workspace. Asking to create the issue on GitHub is rejected.
The workspace also keeps the latest 20 actions, newest first. Reading that list does not add an
event, and the stored rows cannot be updated or deleted.
Feedback bodies stay in the database.

Validate the seed fixtures:

```bash
python -m feedback_hub.seed.validate ../../seed-data
```

## Contributing

All changes land through pull requests into `main`. CI must pass backend and frontend lint,
type checks, unit and integration tests, the frontend production build, seed-data validation,
secret scanning, CodeQL, dependency review, and container scanning.
