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
| `seed-data` | Appwrite seed source and synthetic CSV fixture |
| `.github/workflows` | CI, security, and delivery pipelines |

More workspaces (`apps/web`, workers, `infra/helm`, `supabase`) are added as milestones land.

## Local development

### Backend

```bash
cd apps/api
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

ruff format --check . && ruff check . && mypy
pytest
uvicorn feedback_hub.main:app --reload
```

Validate the seed fixtures:

```bash
python -m feedback_hub.seed.validate ../../seed-data
```

## Contributing

All changes land through pull requests into `main`. CI must pass lint, type checks, unit
tests, seed-data validation, secret scanning, CodeQL, dependency review, and container scanning.
