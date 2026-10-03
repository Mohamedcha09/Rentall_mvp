# SEVOR 47-family rental research extension

Date: 2026-10-03  
Scope: local repository and isolated tests only. No Production database,
deployment, restart, reindex, Git write, mobile project, booking, payment, or
user data was changed.

## Outcome

The active catalog is now one data-driven tree used by Create, Edit, server
validation, Admin display, Explore, Search, and Finder. The 333 supplied
research references are all accounted for in
[rental_research_coverage_2026-10-03.json](rental_research_coverage_2026-10-03.json);
they are not treated as invented inventory or live availability claims.

| Measure | Before research extension | After research extension | Change |
| --- | ---: | ---: | ---: |
| Active L1 | 21 | 22 | +1 |
| Active L2 | 121 | 135 | +14 |
| Active L3 | 701 | 951 | +250 |
| Two-level L2 branches | 25 | 19 | Existing simple branches retained; only useful branches gained L3 |

The before snapshot is
[rental_taxonomy_expanded_inventory.json](rental_taxonomy_expanded_inventory.json).
The exact current tree, including EN/FR/AR labels, is
[rental_research_expanded_inventory_2026-10-03.json](rental_research_expanded_inventory_2026-10-03.json).

## Source of truth and integration

- `app/rental_catalog.py` is the authoritative rental L1/L2/L3 definition.
- `app/catalog_taxonomy.py:CATEGORY_TREE` merges that tree with the unchanged
  Digital Accounts catalog. It is the single tree consumed by the marketplace.
- L1/L2 stay persisted in `categories` / `subcategories`; L3 stays centrally
  defined in code and persists in `Item.third_level`. `Other` uses the existing
  `Item.custom_third_level` field rather than a fourth level.
- Create and Edit obtain database IDs plus L3 choices from
  `catalog_tree_payload`; `resolve_listing_hierarchy` verifies parent-child
  relationships server-side before saving.
- Explore filters the same structured fields. Admin, Details, and Owner views
  render `listing_hierarchy`, so a saved path is not rebuilt from a title.
- Search and Finder now share `taxonomy_path_aliases`. The generated,
  context-aware `app/rental_research_aliases.py` carries 271 active paths and
  280 source-wording aliases; it is not copied into route-specific arrays.

No template list was duplicated or redesigned. The existing progressive
Category → Subcategory → Type form behavior is generic: a two-level branch has
no required third field, while a configured branch has parent-scoped L3 plus
`Other`/custom-name validation.

## What was added and what was deliberately mapped

One new normal L1 was justified and activated:

```text
Test & Measurement Equipment
  Electrical Test Instruments
  Environmental Monitoring
```

New L2 lookup rows are seeded only where necessary: vehicle travel accessories;
automotive workshop and flooring tools; tableware, rigging, interpretation;
commercial kitchen; hydraulic and geotextile tools; small-harvest processing;
pop-up spaces; recording/studio equipment; and the two test/measurement
branches. All other work extends existing L2 branches with useful L3 choices.

Examples of deliberate non-duplication:

- `Power trowel` maps to existing `Concrete & Masonry → Trowels`.
- `Industrial chiller` maps to `Climate Control → Chillers`.
- `Handheld barcode scanner` maps to `POS & Checkout → Barcode Scanners`.
- Fuel, capacity, wheel count, material, and compatibility remain listing
  details/search aliases rather than hundreds of taxonomy nodes.
- Badge molds/cutters, pipe-threading components, hoses, and honey accessories
  are linked to their documented parent kit rather than falsely offered as
  independently proven rentals.
- Crewed yacht charter, heat-press/sewing workstations, and similar cases are
  represented as an active equipment/workspace path plus a documented
  rental-mode condition, not a false extra taxonomy level.

The 333-row status total is:

| Status | Entries |
| --- | ---: |
| ADDED | 225 |
| ALIAS_MAPPED | 60 |
| EXISTING | 12 |
| KIT_COMPONENT_MAPPED | 11 |
| RENTAL_MODE_MAPPED | 4 |
| REVIEW_REQUIRED | 21 |
| **Total** | **333** |

The per-reference rationale, final canonical path, activation state, source
URLs, and test/blocker are in the JSON manifest. The readable working maps
remain available in
[rental_research_mapping_r01_r24.md](rental_research_mapping_r01_r24.md) and
[rental_research_mapping_r25_r47.md](rental_research_mapping_r25_r47.md).
The source URLs are retained as supplied research evidence; a supplier page
does not establish SEVOR inventory, availability, or a legal entitlement to
offer the asset in every market.

## Intentionally review-gated references

The following are reported, not activated as ordinary self-service listings:

- R12 industrial FDM/SLA/SLS printer programs: installed, trained, and often
  long-term arrangements.
- R30 professional laboratory equipment and R41-05 laboratory time slot:
  device, cleaning, temperature-chain, and facility workflow review required.
- R43 mobility equipment: provider and suitability/compliance review required.
- R47 aircraft and helicopter charter: professional charter/compliance,
  insurance, crew, and operational workflow are not modeled by the current
  marketplace.

This preserves their research trace without misrepresenting them as ready for
instant booking. Digital Accounts remains present and unchanged.

## Migration and operator step

`db_migrations/versions/20261005_expand_research_rental_catalog.py` is the
forward-only, immutable L1/L2 delta for the normal local/staging lineage. It
uses only missing-row inserts, rejects ambiguous lookup rows, does not import
the live catalog at migration runtime, and never deletes, renames, reorders,
or reclassifies listings.

For the observed Render production base, use the separate immutable branch
`20261005_research_taxonomy_production_bridge.py` and target
`research_bridge_20261005`; it applies the base taxonomy bridge plus this
same research delta without traversing the unrelated Finder lineage. The
repository converges later at `merge_research_taxonomy_20261005`. See
`render_taxonomy_bridge_runbook.md` for the backup, preflight, write, and
verification sequence. No production command was executed during this work.

For a **separately chosen isolated development/test database only**, after
reviewing the code, run:

```powershell
$env:PYTHONPATH = (Get-Location).Path
alembic upgrade head
```

Do not point that command at Production as part of this local task. No deploy
or Production migration was performed here.

## Test evidence

Executed against isolated SQLite databases or data-only modules:

- `tests.test_rental_research_manifest` verifies all 333 exact references,
  every active target path, translations, and all 280 aliases through both
  Search and Finder.
- `tests.test_rental_catalog` verifies tree depth, translations, duplicate
  sibling labels, compatibility aliases, and immutable migration parity.
- `tests.test_item_taxonomy` verifies every configured Create payload path in
  EN/FR/AR and the shared server resolver.
- `tests.test_item_taxonomy_route_flow` exercises actual HTTP routes:
  Create → save → Pending Admin → approve → Explore filter → Details → Edit,
  including Digital Accounts, a normal two-level path, `Other`, old untyped
  data, and `Test & Measurement Equipment → Electrical Test Instruments →
  Ground Resistance Testers`.
- `tests.test_finder` was run in its own isolated process. Source aliases
  resolve to structured taxonomy paths without blocking live-title discovery
  for future dynamic categories.

The form was validated through rendered HTTP responses and serialized DOM
payloads, not a physical phone/browser visual test. No claim is made for a
physical iPhone/Android or Production visual verification.

## Files changed for this extension

| File | Role |
| --- | --- |
| `app/rental_catalog.py` | Additive catalog branches, translations, duplicate-label guard, central path-alias API. |
| `app/rental_research_aliases.py` | Generated context-aware aliases derived from active manifest mappings. |
| `app/catalog_taxonomy.py` | Exposes the shared alias helper alongside the existing unified tree. |
| `app/routes_search.py` | Uses the shared aliases for structured taxonomy search. |
| `app/finder_service.py` | Uses the shared aliases while preserving bounded future-title discovery. |
| `db_migrations/versions/20261005_expand_research_rental_catalog.py` | Additive, immutable L1/L2 lookup seed. |
| `tests/test_rental_research_manifest.py` | Exact 333-reference, path, Search, and Finder coverage. |
| Existing taxonomy tests | Updated counts/head expectations and route-flow coverage for the new L1. |
| `docs/rental_research_*` | Before/after inventory, full coverage manifest, source alias export, readable mapping, and this report. |

## Out-of-scope observation

Running unrelated suites together can load the repository's pre-existing
default local SQLite file before `tests.test_finder` replaces `DATABASE_URL`;
that stale file lacks `notifications.opened_once`. Finder passes when run as its
documented isolated process. This was not changed because it is unrelated to
the catalog expansion.
