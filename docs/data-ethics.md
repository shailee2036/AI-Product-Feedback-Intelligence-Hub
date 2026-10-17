# Data ethics

This describes the data the running app stores. Public GitHub issues are still personal data and are still subject to GitHub's terms.

## What is imported

- Public issues from one organization-owned GitHub repository that has a recognized open-source license.
- An optional CSV of feedback for that same product. The committed Appwrite CSV is synthetic. It is not a record of real Appwrite customer complaints, and it does not claim that Appwrite has those defects.

Issue bodies are fetched when the user runs an import. The repository does not redistribute a third-party issue corpus.

## What is kept

- Issue title, body, labels, counts, state, URL, and timestamps needed to show the source.
- A SHA-256 hash of the GitHub user node id. The login and email are not stored as the author.
- Uploaded CSV rows after validation. Personal data in free text is redacted before a model sees the text.

Security-labeled issues are skipped. The app does not keep avatars.

## Telemetry

Staging sends API metrics, API logs, and API traces to a Grafana Cloud stack. They carry counts, durations, route templates, operation, provider, and model names. They do not carry issue text, CSV rows, prompts, embeddings, briefs, repository names, user names, or ids. Grafana Labs keeps that copy for the stack's retention period, separately from the in-cluster copy.

## What a person can see

Theme evidence links back to the GitHub issue or the uploaded row. Generated names and briefs are labeled as generated. A person can rename a theme, approve or dismiss it, merge or split it, and edit a brief. Those edits are the human record.

## Deletion

Deleting a workspace row is the supported removal path for data this app stored. It does not delete the original GitHub issue. Public availability of an issue does not remove GitHub's terms or the person's privacy interest in the text.
