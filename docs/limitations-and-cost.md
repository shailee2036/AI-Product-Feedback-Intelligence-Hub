# Limitations and cost

## Limitations

- One workspace registers one public, organization-owned GitHub repository with a recognized license.
- Theme naming calls the model only for themes that do not already have a name. A second click does not create another provider call.
- A failed import stays failed. Run the import again after GitHub is reachable.
- Confirming a new-issue draft saves it in the workspace. It does not open a GitHub issue.
- Grafana charts for model providers show the staging API only. Clicks handled by the API on a laptop do not appear there.
- Provider charts show a rate. A few calls look like a small fraction of a request per second.
- Metrics, logs, and traces in the cluster are lost when the observability pod moves, because they sit on an `emptyDir`. The Grafana Cloud copy keeps API telemetry for the free tier's 14 days.
- Alerts are evaluated by the in-cluster Prometheus only. Grafana Cloud has the dashboards but no alert rules.
- No load test was run. There is no production cluster.

## Cost

Grafana shows reported tokens and embedding text counts. The Spend dashboard adds USD only when a per-million rate is configured, and that rate defaults to zero. It is not read from a provider invoice.

What staging actually runs:

| Piece | What you pay for |
| --- | --- |
| Oracle Kubernetes, `us-phoenix-1` | One always-on ARM node. This is the infrastructure bill. The app does not read the Oracle invoice. |
| Supabase | Auth, Postgres, and `pgvector` for the project. The bill follows that project's plan. |
| Groq | Free plan. Theme names and briefs use `openai/gpt-oss-20b` until the free-plan limit is reached. |
| Gemini | Embeddings with `gemini-embedding-001`. Usage follows the Google project attached to the API key. |
| GitHub | Public API reads, Actions minutes, and the container registry. |
| Grafana Cloud | Free tier. Receives API metrics, API logs, and API traces only, well under the free series and volume limits. |
| GPU, model weights, LiteLLM on the cluster | Not deployed. |

Token counts in Grafana are not a substitute for the Groq, Gemini, Supabase, or Oracle invoices.
