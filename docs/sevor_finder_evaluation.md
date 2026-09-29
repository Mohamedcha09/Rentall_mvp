# Sevor Finder evaluation corpus

`tests/fixtures/finder_quality_evaluation.json` is a versioned, offline
quality corpus for Sevor Finder.  It contains 128 single-turn requests and 20
multi-turn conversations across Arabic, French, English, Arabizi and mixed
French/English phrasing.  It deliberately covers normal search wording,
unusual categories, product details, prices and units, locations, availability,
pagination, comparisons, state changes, support-boundary requests and
prompt-injection-shaped listing text.

The fixture is **not** loaded by the Finder application or provider prompt.
It must remain independent from routing rules.  A passing corpus structure
test is not a claim that all language understanding is solved; it protects the
coverage set from accidental shrinkage and gives reviewers a stable holdout
slice.

Run the offline checks with:

```powershell
python -m unittest tests.test_finder tests.test_finder_quality_corpus
```

`tests.test_finder` creates an isolated SQLite database and exercises the real
Finder HTTP API plus the catalog query.  It covers authentication, CSRF,
conversation ownership, duplicate submissions, live listing revalidation,
public-only visibility, exact target-price ranking, hard price ceilings,
missing exchange-rate behavior, booking-date conflicts, pagination, generic
new-category indexing, prompt-injection text, state revisions and the Support
boundary.  It has no provider key and therefore does not claim a live LLM
evaluation.  A provider-on review must be run separately in an authorized
staging environment after `SEVOR_FINDER_PROVIDER_PARSE=1` and provider
credentials are configured.
