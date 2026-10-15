# 0002. GitHub writes stay confirmed

## Status

Accepted. The default demo does not write to GitHub.

## Context

The product recommends an existing GitHub issue for each theme. Creating or editing an issue from imported text can spam a public repository.

## Decision

Imports and repository checks only read the GitHub API. A new-issue draft is stored in the workspace. Confirming that draft does not create a GitHub issue. Any future write still requires an explicit confirmation from a signed-in member.

When GitHub cannot be reached, the import is marked failed with `GitHub did not respond.` The address that failed is not stored.

## Consequences

The demo cannot open an issue by itself. A failed import does not resume; the user starts a new import after GitHub is reachable.
