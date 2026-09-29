# Sevor Finder

Sevor Finder is a signed-in, read-only rental-catalog assistant. It has its
own conversations, messages, and search state and never creates a Support
ticket or a direct-message thread. The server—not a language model—decides
which listings are public, applies filters, checks price comparability and
availability, ranks results, and creates listing links.

## Deployment sequence

1. Apply the additive Alembic migration:

   ```powershell
   alembic upgrade head
   ```

2. Build the derived index once after the migration:

   ```powershell
   python -m app.finder_index --rebuild
   python -m app.finder_index --coverage
   ```

   The rebuild reads only listings that are currently `approved` and active.
   It never changes a listing, price, status, booking, Support ticket, or
   direct message. Live catalog data remains authoritative: a result is
   rechecked when it is returned and when historical Finder cards are read.

3. Deploy the application and use `/finder`. The endpoint requires an
   authenticated SEVOR user and uses the existing CSRF/session protection.

No migration, rebuild, or deployment is performed by this implementation task.

## Index maintenance

`FinderListingIndex` is derived from public `Item` text and explicit attributes.
Lifecycle hooks update/remove its row when an item is approved, edited,
resubmitted, rejected, reset, deleted, or hidden by moderation. The initial
rebuild is still required for existing catalog entries. `--coverage` reports
eligible versus indexed listing counts.

The index extracts only text explicitly present in title, description, or
subcategory. It records the source and does not infer doors, sizes, condition,
or other claims from an image. Unknown attributes remain unknown rather than
being treated as confirmed matches.

## Provider mode and fallback

Finder has a deterministic multilingual parser and works without an AI
provider. If the established SEVOR provider is configured and has passed
staging evaluation, parsing enrichment can be enabled deliberately with:

```text
SEVOR_FINDER_PROVIDER_PARSE=1
SEVOR_FINDER_PROVIDER_TIMEOUT_SECONDS=10
```

It reuses the existing provider configuration (`OPENAI_API_KEY`,
`SEVOR_AI_PROVIDER`, and `SEVOR_AI_MODEL`) without exposing any credential to
the browser. The provider receives a bounded search schema and category hints;
it cannot receive an ORM session, SQL, private customer data, listing URLs, or
permission to create actions. Its suggestion is validated against an allowlist
before the deterministic server search runs. On timeout, invalid JSON, or an
unavailable provider, Finder retains the request and uses the deterministic
fallback instead of fabricating results.

## Current scope and operational limits

- All active, approved `Item` categories are eligible dynamically; the service
  does not maintain a hard-coded list of rentable product categories.
- Price limits and target-price ordering use current `FxRate` data only. A
  cross-currency listing is not treated as within a hard ceiling when no valid
  conversion exists.
- Availability is checked only for a valid supplied ISO date range. Without
  dates, cards correctly say confirmation is required rather than claiming
  availability.
- The direct live scan is intentionally bounded. If the catalog exceeds the
  safe candidate limit, the response identifies that the count is not an
  exhaustive catalog claim until index operations are expanded appropriately.
- Natural-language date formats, radius search, owner-entered structured
  quantities, and arbitrary cross-script brand transliteration depend on the
  quality of the underlying listing data and staged provider evaluation. They
  must not be represented as verified facts when the listing does not state
  them.

## Tests

Run the offline Finder integration suite with:

```powershell
python -m unittest tests.test_finder -v
```

The suite uses an isolated SQLite catalog and verifies public-only results,
ownership, CSRF, idempotency, target/maximum price behavior, currency handling,
availability, pagination, dynamic categories, prompt-injection-as-data,
historical-card revalidation, and separation from Support. A separately
configured staging run is required before claiming that a live provider works.
