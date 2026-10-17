# Threat model

The system is a single-tenant demo workspace: one signed-in user, one public repository, and optional CSV rows. Staging runs on one Oracle Kubernetes node. Secrets live in Kubernetes and in Supabase, not in git.

## Assets

- Supabase JWT signing keys and the database URL.
- The GitHub token, Groq key, and Gemini key.
- Imported issue text, CSV rows, embeddings, and generated briefs.
- The Grafana admin password and the alert email password.
- The Grafana Cloud access-policy token. It can write metrics, logs, and traces to the stack but cannot read them.

## Trust boundaries

- The browser talks to the Next.js site. The site calls the API with the user's Supabase access token.
- The API is the only component that calls GitHub, Groq, and Gemini.
- Prometheus scrapes the API. Logs and traces leave the API pod only as allowlisted fields. Raw feedback, prompts, embeddings, and briefs are not log or span fields.
- When the Grafana Cloud copy is on, API metrics, API logs, and API spans leave the cluster for Grafana Labs over HTTPS. Logs and metrics from the other pods are filtered out before sending. The same allowlists apply, so the stack holds counts, route templates, and operation names, not feedback text.
- GitHub is an untrusted content source. Issue text is data, not instructions to run.

## What the app resists

- A request without a valid Supabase JWT cannot read or change workspace rows.
- Database sessions use the authenticated role and row-level security.
- Private, missing, archived, and unlicensed repositories are rejected.
- Model output that cites an evidence id the server did not provide is rejected.
- A connection error from GitHub is stored as `GitHub did not respond.` The host is not stored.
- FastAPI's own telemetry is off, so a request span does not carry the raw URL path.

## What this release does not claim

- There is no production environment and no second tenant in staging.
- GitHub webhooks are not implemented, so there is no webhook signature check.
- The app does not delete a GitHub issue, and confirming a new-issue draft does not create one.
- Observability disks are `emptyDir`. A reschedule drops the in-cluster metrics, logs, and traces. The Grafana Cloud copy keeps them for the stack's retention period.
- Load testing was not run.
- Alert email and the Grafana password are cluster secrets. Losing the cluster secrets means those credentials must be rotated.
