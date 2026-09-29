# Sevor AI operating modes and safe configuration

## Operating modes

The chatbot records one explicit mode for every automatic answer in its message
metadata:

| Mode | Meaning |
| --- | --- |
| `llm_conversation_active` | A configured provider returned a response after the server had selected approved knowledge and/or safe tool facts. |
| `knowledge_only_fallback` | No configured provider is available; the server answered from approved knowledge, deterministic conversation handling, or a safe clarification. |
| `provider_unavailable` | A configured provider could not answer; the server retained the safe knowledge fallback rather than pretending that the provider answered. |

`provider_readiness` is intentionally separate: it is `llm_configured` only
when all of `SEVOR_AI_PROVIDER=openai`, `SEVOR_AI_MODEL`, and
`OPENAI_API_KEY` are available. It is otherwise `knowledge_only_fallback`.
Configuration is not proof of a successful provider call; only the first mode
above is.

## Required provider configuration

Configure these values in the environment used by the web process, never in
source control:

```text
SEVOR_AI_PROVIDER=openai
SEVOR_AI_MODEL=<approved Responses API model>
OPENAI_API_KEY=<server-side secret>
```

No browser receives the provider key. The server uses the existing Responses
API adapter with bounded recent history, a structured conversation summary,
retrieved approved excerpts, and narrowly allow-listed safe tool results.

## Data boundary

The model never chooses a user ID, SQL query, ORM session, URL fetch, or write
operation. Server-side tools use the authenticated session and can only return
current-user, read-only facts. The provider receives only the explicitly
allow-listed fields needed to phrase an answer; listing titles, free-form text,
email addresses, telephone numbers, internal notes, credentials, and payment
secrets are excluded. ISO booking dates remain available when authorized.

The deterministic fallback continues to work when the provider is unavailable.
It can answer grounded knowledge questions, ask a focused clarification, and
use the existing human-support handoff. It must not invent a commercial policy
or personal account result.

## Knowledge maintenance

Approved knowledge lives in `app/chatbot/approved_knowledge.json`. Each entry
can record its source, source version, review state, update date, symptoms,
troubleshooting, follow-up questions, and escalation conditions. The loader
uses the file revision (mtime and size), so an approved JSON update is picked
up without a stale in-process knowledge cache.

`app/chatbot/knowledge_gaps.json` is an internal approval queue, not a source
of customer-facing facts. Add a policy there when its published source is
missing or conflicts with runtime behavior; promote it to approved knowledge
only after an owner approves a source and wording.

## Limits and failure behavior

- Recent history and summary are bounded before a provider request.
- Retrieval uses a bounded hybrid search and makes at most one contextual retry.
- Tools are read-only, validated, authorization-checked server-side, and return
  an explicit unavailable result on service failure rather than a false
  "nothing found" claim.
- Sensitive credentials and prompt-injection attempts are blocked/redacted
  before persistence and provider use.
- A human handoff stops automatic responses according to the existing
  conversation state; an AI response is rechecked before it is saved.

This document describes local source behavior. It does not claim that a
provider is configured or that these changes are deployed.
