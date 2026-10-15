# 0001. Use managed inference

## Status

Accepted. This is what the API ships.

## Context

Theme names, product briefs, and embeddings need a model. Hosting weights would require a GPU node and a model-serving deployment.

## Decision

Generation goes to Groq on the free plan. The default model is `openai/gpt-oss-20b`. Embeddings go to Gemini `gemini-embedding-001`. If `FEEDBACK_HUB_LITELLM_BASE_URL` is set, generation is sent to that proxy instead of Groq. The staging cluster does not run LiteLLM.

The API records provider, model, result, latency, and reported token counts. It does not estimate a dollar cost.

## Consequences

There is no GPU node and no model image in the cluster. Groq's free-plan limits can stop naming and brief writing until the limit resets. Embedding vectors from another model must not be mixed into the same index.
