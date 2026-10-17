# Personal model credentials

Graph search, source evidence, relationship exploration and read-only MCP work
without a model. Optional written synthesis uses only the signed-in user's own
credential. There is no operator-key fallback, including when the deprecated
`GP_LLM_*` environment settings contain values.

In Settings, choose OpenRouter or OpenAI, enter a supported Chat Completions model
ID and your personal API key, then save. Saving does not contact the provider.
When you ask a repository question, bounded source excerpts and graph
relationships are sent to the chosen provider. The provider bills your account;
GraphPilot does not supply credits. Free-model availability and quotas are
controlled by the provider. Private verification uses free models only.

Credentials are encrypted in PostgreSQL with the deployment's durable
`GP_CREDENTIAL_KEY`. The same key must be available to API processes after
restart or restore. Preserve it with protected backups; do not rotate it without
a credential migration. API responses return only provider/model/status, never a
key or suffix. The form keeps the key in component memory, clears it after a
save attempt or navigation, and does not use browser storage for it.

The browser API is `GET`, `PUT` and `DELETE /api/model`. Mutations require an
authenticated browser session, an allowed origin and CSRF. CLI credentials cannot
manage keys. Synthesis requests from authorized repository/CLI contexts resolve
the current user's credential, including when several users share a repository.
MCP tools do not invoke a model. Fixed HTTPS provider endpoints prevent custom
credential URLs from accessing internal services. Provider failures, malformed
answers, unusable credentials and invalid citations retain graph results.

Remove or replace credentials in Settings. Removal stops future use of that
live database record; protected backups may retain older encrypted records.
Revoke the key with the provider too if it should become unusable everywhere.
Provider-side revocation is separate from removing a GraphPilot record.

Deployment requires migration `0011` and an existing durable encryption key.
Deploy API and frontend together, then verify graph-only behavior and two-user
isolation. Never put a provider key in frontend build variables, Docker images,
repository files or a shared server fallback.

References: [OpenRouter Chat Completions](https://openrouter.ai/docs/api_reference/overview),
[OpenRouter free routing](https://openrouter.ai/docs/guides/routing/model-variants/free),
[OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
