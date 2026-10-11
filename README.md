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
| `supabase/migrations` | Postgres schema and row-level security policies (source of truth) |
| `supabase/tests` | SQL row-level security tests and a Supabase auth stub for plain Postgres |
| `seed-data` | Appwrite seed source and synthetic CSV fixture |
| `compose.yaml` | Local Postgres (pgvector) and Redis for integration tests |
| `.github/workflows` | CI, security, and delivery pipelines |

More workspaces (`apps/web`, workers, `infra/helm`, `supabase`) are added as milestones land.

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

Validate the seed fixtures:

```bash
python -m feedback_hub.seed.validate ../../seed-data
```

## Contributing

All changes land through pull requests into `main`. CI must pass lint, type checks, unit
tests, seed-data validation, secret scanning, CodeQL, dependency review, and container scanning.
