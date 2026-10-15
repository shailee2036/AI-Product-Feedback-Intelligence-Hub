# 0003. Supabase for auth and rows

## Status

Accepted.

## Context

The app needs accounts, a Postgres database, and vector storage for one product workspace.

## Decision

Supabase Auth issues the JWT. The API checks the issuer, audience, signature, and expiry. Postgres holds the product, imports, feedback rows, embeddings, and themes. Row-level security applies because API queries run as the authenticated role with the caller's JWT claims. Vectors use `pgvector` in that same database.

## Consequences

Sign-in, the database, and the vectors are one vendor. A workspace cannot query another tenant's rows through the API. Local development and staging can point at the same Supabase project; metrics still belong to whichever API process handled the request.
