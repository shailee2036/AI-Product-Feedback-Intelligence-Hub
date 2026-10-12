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

Exact duplicates share a hash of the redacted text. Semantic duplicates are mutual nearest
neighbors with cosine similarity of at least 0.86. A starter set of labeled seed pairs is scored
with each run. The full 200-pair review is later manual labeling.

Candidate themes are mutual nearest neighbors with cosine similarity of at least 0.82 and at
least three rows. A starter set of seed themes is scored with each run. Naming sends up to six
redacted titles per theme to Groq in one request and stores a short name and summary. A name
already stored, including one marked as edited, stays in place. Approving a theme keeps it
when themes are found again. Open and dismissed themes are replaced. Merge moves every row
into another theme. Split moves the selected rows into a new theme.

Validate the seed fixtures:

```bash
python -m feedback_hub.seed.validate ../../seed-data
```

## Contributing

All changes land through pull requests into `main`. CI must pass backend and frontend lint,
type checks, unit and integration tests, the frontend production build, seed-data validation,
secret scanning, CodeQL, dependency review, and container scanning.
