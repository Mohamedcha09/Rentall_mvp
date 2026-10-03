# SEVOR rental taxonomy audit and local expansion

Date: 2026-10-03  
Scope: local repository only; no production database, deployment, restart, reindex, or Git write was performed.

## A. Current inventory before the change

The recorded baseline is [rental_taxonomy_before_2026-10-03.json](rental_taxonomy_before_2026-10-03.json).

- Runtime L1/L2 truth was `categories` / `subcategories`; item rows retain text values in `category`, `subcategory`, `third_level`, and `custom_third_level`.
- Runtime L3 truth was `app/catalog_taxonomy.py:CATEGORY_TREE`.
- Before this expansion, the only version-controlled configured L3 catalog was `Digital Accounts`: 1 L1, 17 L2, and 346 L3 values.
- Both checked-in local SQLite lookup snapshots had zero `categories` and `subcategories` rows. Therefore this audit does **not** invent a complete pre-existing ordinary-rental tree.
- Local historical items used legacy L1 values (`vehicle`, `housing`, `electronics`, `furniture`, `tools`), with no saved L2/L3 values in the inspected snapshots.
- `Category.name` is unique, but `Subcategory(category_id, name)` has no database uniqueness constraint. The new migration detects ambiguity rather than deleting or merging it.
- There are no taxonomy slugs, enabled flags, sort fields, L3 lookup table, or taxonomy-management admin UI in the inspected schema.

This distinguishes catalog definition from listings: a branch with zero listings is still a valid available category.

## B. Expanded active catalog

The single authoritative active definition is [app/rental_catalog.py](../app/rental_catalog.py). It contains every canonical L1/L2/L3 node and its English/French/Arabic labels; it intentionally avoids a second hand-maintained catalog in templates, validators, or Finder. The generated review export is [rental_taxonomy_expanded_inventory.json](rental_taxonomy_expanded_inventory.json), which contains every active path and all three labels. `Digital Accounts` remains in [app/catalog_taxonomy.py](../app/catalog_taxonomy.py) unchanged as its established 17-L2/346-L3 catalog.

After the expansion, central code defines 21 L1 values, 121 L2 values, and 701 L3 values. Of the 121 branches, 25 deliberately remain two-level branches and 96 use an optional third level. The 20 non-Digital rental L1 definitions add 104 L2 and 355 L3 values; database net-new totals may be lower where a compatible legacy parent already exists.

| Canonical L1 | Français | العربية | L2 / L3 |
| --- | --- | --- | ---: |
| Vehicles | Véhicules | المركبات | 6 / 42 |
| Housing & Stays | Logements et séjours | السكن والإقامات | 4 / 0 |
| Electronics | Électronique | الإلكترونيات | 5 / 23 |
| Furniture | Mobilier | الأثاث | 5 / 0 |
| Clothing & Costumes | Vêtements et costumes | الملابس والأزياء التنكرية | 4 / 8 |
| Tools & Equipment | Outils et équipement | الأدوات والمعدات | 6 / 15 |
| Baby & Kids | Bébés et enfants | الأطفال والرضع | 4 / 0 |
| Sports & Outdoors | Sports et plein air | الرياضة والأنشطة الخارجية | 6 / 17 |
| Books & Learning | Livres et apprentissage | الكتب والتعلم | 4 / 4 |
| Events & Production Equipment | Équipement événementiel et de production | معدات المناسبات والإنتاج | 8 / 30 |
| Food & Concession Equipment | Équipement de restauration et de concession | معدات الطعام وأكشاك البيع | 8 / 37 |
| Construction & Industrial Equipment | Équipement de construction et industriel | معدات البناء والصناعة | 7 / 30 |
| Agriculture & Landscaping | Agriculture et aménagement paysager | الزراعة وتنسيق الحدائق | 5 / 18 |
| Warehousing & Logistics | Entreposage et logistique | المستودعات واللوجستيات | 5 / 20 |
| Temporary Infrastructure & Site Services | Infrastructure temporaire et services de chantier | بنية تحتية مؤقتة وخدمات موقع | 7 / 31 |
| Marine & Watercraft | Maritime et embarcations | البحرية والمراكب | 3 / 12 |
| Spaces & Studios | Espaces et studios | مساحات واستوديوهات | 5 / 20 |
| Retail & Vending Equipment | Équipement de commerce et de vente | معدات التجزئة والبيع | 4 / 16 |
| Music & Performance Equipment | Équipement musical et de spectacle | معدات الموسيقى والعروض | 4 / 16 |
| Hobbies & Creative Equipment | Équipement de loisirs et création | معدات الهوايات والإبداع | 4 / 16 |
| Digital Accounts | Comptes numériques | الحسابات الرقمية | 17 / 346 |

Full canonical branch index (the exact translated leaf values are co-located with these nodes in `rental_catalog.py`):

```text
Vehicles
  Cars; Buses; Trucks & Vans; Trailers & RVs;
  Bicycles & Micro-mobility; Motorcycles & Scooters
Housing & Stays
  Apartments & Homes; Vacation Properties; Rooms & Shared Stays; Parking & Storage
Electronics
  Computers & Tablets; Cameras & Video; Networking & Communications;
  Office Tech; Gaming & VR
Furniture
  Home Furniture; Office Furniture; Event Furniture; Appliances; Rugs & Decor
Clothing & Costumes
  Formal & Bridal; Costumes & Theatrical; Outdoor & Specialty; Accessories
Tools & Equipment
  Power Tools; Hand Tools; Plumbing & Pipe Tools; Electrical & Testing Tools;
  Cleaning & Restoration Equipment; Surveying & Inspection
Baby & Kids
  Travel & Safety; Nursery & Sleep; Toys & Play; Party & Event Gear
Sports & Outdoors
  Camping & Outdoors; Winter Sports; Water Sports; Fitness Equipment;
  Team Sports; Fishing Equipment
Books & Learning
  Books; Classroom Equipment; Lab & Science Kits; Training & Presentation
Events & Production Equipment
  Tents & Canopies; Staging & Flooring; Audio Equipment; Lighting Equipment;
  Video & Displays; Photo Booths & Signage; Crowd Control & Safety; Event Furniture
Food & Concession Equipment
  Popcorn Equipment; Hot Dog Equipment; Donut Equipment;
  Frozen & Dessert Equipment; Cooking Equipment; Serving & Beverage Equipment;
  Mobile Food Units; Sanitation & Dishwashing
Construction & Industrial Equipment
  Earthmoving; Aerial Access; Concrete & Masonry; Compaction & Paving;
  Air & Pneumatic; Welding & Fabrication; Trench & Shoring
Agriculture & Landscaping
  Tractors & Implements; Lawn & Garden; Forestry & Tree Care;
  Irrigation & Water; Livestock & Farm Handling
Warehousing & Logistics
  Forklifts & Telehandlers; Pallet & Manual Handling; Storage & Containers;
  Loading & Dock; Packaging & Labeling
Temporary Infrastructure & Site Services
  Power Generation; Climate Control; Drying & Air Quality; Sanitation;
  Fencing & Traffic Control; Mobile Offices & Structures; Pumps & Water Management
Marine & Watercraft
  Boats; Personal Watercraft; Marine Gear
Spaces & Studios
  Event Venues; Studios; Meeting & Workspaces; Workshops & Maker Spaces;
  Commercial Kitchens
Retail & Vending Equipment
  Display & Merchandising; POS & Checkout; Kiosks & Booths;
  Vending & Refrigerated Merchandising
Music & Performance Equipment
  Musical Instruments; DJ Equipment; Amplification & Backline;
  Rehearsal & Performance Gear
Hobbies & Creative Equipment
  Printing & Fabrication; Sewing & Textile; Arts & Crafts; Games & Recreation
```

Representative complete paths:

```text
Vehicles → Buses → School Buses
Food & Concession Equipment → Popcorn Equipment → Popcorn Machines
Food & Concession Equipment → Hot Dog Equipment → Hot Dog Rollers
Food & Concession Equipment → Donut Equipment → Donut Makers
Temporary Infrastructure & Site Services → Sanitation → Portable Toilets
Spaces & Studios → Studios → Podcast Studios
Digital Accounts → Movies & Streaming → Amazon Prime Video
```

`Other` is only an L3 option where a branch has meaningful sibling choices. It stores its free text in `custom_third_level`; it is not a fourth level. No tag combination such as colour/year/fuel/capacity was turned into taxonomy.

## C. Compatibility and duplicate policy

- Existing listing strings are never rewritten by the rental expansion.
- Declared legacy L1 aliases (`vehicle`, `housing`, `electronics`, `furniture`, `clothing`, `tools`, `sports`, `Sports Equipment`, `books`) resolve to their new presentation/tree parent only for lookup, display, search, and validation. Their stored values remain intact.
- A legacy L1-only item such as `vehicle` remains editable without a forced L2 after that parent gains children. This Edit-only compatibility path requires the unchanged, equivalent parent and blank child fields; it preserves the raw stored value rather than guessing a new branch. It also tolerates a single canonical lookup parent when a legacy alias row is absent, while ambiguous lookup matches fail closed. New or moved paths persist the resolved lookup-row value rather than a browser-supplied alias.
- A pre-existing `Vehicles → Cars` listing with no L3 remains editable on the unchanged path. It is shown under Vehicles and Cars, but it does not falsely match a chosen L3 such as Sports Cars.
- New creates and edits that move into a configured three-level branch must select a valid L3.
- Moving from a three-level branch to a two-level branch clears `third_level` and `custom_third_level` atomically.
- Cross-context duplicate equipment names were reviewed. Portable water gear stays under Sports rather than Marine Gear; event video uses switchers/streaming kits rather than duplicating Electronics projectors; temporary site equipment owns temporary fencing, portable sanitation, HVAC, and dehumidification.

## D. Research basis

Sources were consulted on 2026-10-03. They demonstrate that these are actual rental families; they do not prove demand, supply, insurance availability, or legal eligibility in every SEVOR market.

- North American construction, events, temporary power, lighting, generators, fencing, and barricades: [United Rentals event equipment](https://www.unitedrentals.com/solutions/industry-solutions/events-entertainment).
- Temporary heating, cooling, dehumidification, air handling, and air quality: [Sunbelt climate-control catalog](https://www.sunbeltrentals.com/equipment-rental/heating-cooling-air-management/).
- Agricultural, forestry, tractor, trailer, and material-handling rental families: [Sunbelt agriculture equipment](https://www.sunbeltrentals.com/industries/agriculture-equipment/).
- French-language construction, handling, power, temporary-site, sanitation, and event rental evidence: [LOXAM Event](https://www.loxam.fr/evenements) and [Kiloutou](https://www.kiloutou.fr/).
- Food-concession equipment evidence: [Plan-It concession rentals](https://www.planitrentals.com/concession-machine-rentals).
- Watercraft families: [Boatsetter boat rentals](https://www.boatsetter.com/boat-rentals).
- Event, meeting, workshop, photo, film, and recording spaces: [Peerspace](https://www.peerspace.com/).
- Temporary retail/POS equipment: [Shopify POS hardware rental](https://www.shopify.com/pos/store/pages/hardware-rental-program).

## E. Special review: intentionally not activated

- **Aviation / crewed charter:** not an active self-service category. Canadian guidance distinguishes dry lease, crewed/wet arrangements, and charter, with licensing, custody/control, crew, and maintenance implications. See [Transport Canada’s leasing guidance](https://tc.canada.ca/en/aviation/reference-centre/advisory-circulars/advisory-circular-ac-no-203-002). A future category needs a separate compliance/insurance/verification workflow.
- **Medical and mobility devices:** not activated as a general category. Health Canada’s MDEL guidance includes offering a medical device for lease within “sell”; enable only after jurisdiction-specific provider/compliance review. See [GUI-0016](https://www.canada.ca/en/health-canada/services/drugs-health-products/compliance-enforcement/establishment-licences/directives-guidance-documents-policies/guidance-medical-device-establishment-licensing-0016.html).
- **Operator, crew, installation, or delivery:** these describe commercial terms, not a type of asset, and were not encoded as L3 values.
- **Digital Accounts:** retained, not recreated, and left in its existing central service taxonomy.

## F. Implementation

| File | Purpose |
| --- | --- |
| `app/rental_catalog.py` | New immutable-in-process central rental definition, labels, aliases, topology safeguards, and seed contract. |
| `app/catalog_taxonomy.py` | Merges the rental tree with Digital Accounts; provides one validation/presentation/translation path, including generic `Other` labels. |
| `app/database.py` | Uses `DATABASE_URL_FULL` when `DATABASE_URL` is absent and refuses a silent SQLite fallback on Render. |
| `db_migrations/versions/20261004_expand_rental_catalog.py` | New additive static L1/L2 seed migration, revision `rental_catalog_20261004` after `digital_catalog_20261003`; no Item rewrite or deletion. |
| `db_migrations/versions/20261004_taxonomy_production_bridge.py` | Scoped idempotent bridge from the observed production base; adds only the three nullable Item taxonomy columns, the taxonomy index, and L1/L2 lookup rows without Finder. |
| `db_migrations/versions/20261004_merge_taxonomy_bridge.py` | Records one future repository head without stamping the un-applied Finder lineage. |
| `scripts/render_taxonomy_preflight.py` | Read-only, secret-safe Render preflight and post-check for backend, schema, revision, and all configured L1/L2 rows. |
| `app/items.py` | Preserves unchanged legacy one- and two-level edit paths while requiring L2/L3 for new or moved configured paths; Explore reads compatible L1 aliases without rewriting rows. |
| `app/templates/items_new.html` / `items_edit.html` | Data-driven labels and L3 prompts, progressive behavior, localized generic validation copy, and accessible client-side option filters that preserve a selected native option. |
| `app/finder_service.py` / `app/routes_finder.py` | Finder reads configured plus lookup taxonomy, including zero-listing categories, without per-category rules. |
| `app/routes_search.py` | Search resolves exact EN/FR/AR taxonomy labels and legacy L1 aliases against structured taxonomy fields. |
| `tests/test_rental_catalog.py`, `tests/test_item_taxonomy.py`, `tests/test_item_taxonomy_route_flow.py` | Topology, compatibility, migration, and full route-flow regression coverage. |

The migration has an immutable tuple snapshot rather than importing mutable application data. It takes a PostgreSQL transaction advisory lock, inserts only missing rows, recognizes a single compatibility parent alias, and fails closed on ambiguous case-insensitive parent or child duplicates. Its `downgrade()` is intentionally forward-only to avoid deleting lookup data.

## G. Test evidence

All database tests used temporary SQLite files, never `app.db`, `database.db`, or a production connection.

- `tests.test_rental_catalog`: 5 passing checks for no missing parent, no duplicate sibling, depth at most 3, translation presence, aliases, and an immutable L1/L2 migration-seed contract.
- `tests.test_item_taxonomy`: 9 passing checks for every Create-form payload node in EN/FR/AR, every resolver path, forged relationships, Digital Accounts, `Other`, representative rental branches, alias normalization, and legacy blank-L3 compatibility.
- `tests.test_item_taxonomy_route_flow`: 3 passing isolated migrations/HTTP flows.
- `tests.test_database_connection_selection` and `tests.test_taxonomy_production_bridge`: 3 passing checks for `DATABASE_URL_FULL`, Render fail-closed behavior, and the scoped production-base migration.
- `tests.test_finder`: 30 passing isolated checks for configured zero-listing branches, lookup-table additions, localized taxonomy matching, and legacy category compatibility.
- Complete Create-form coverage audit: with all central lookup rows seeded in an isolated SQLite database, the real `_taxonomy_form_payload` exposed exactly 21 L1, 121 L2, and 701 L3 values in English, French, and Arabic. The real resolver accepted all 25 two-level paths and all 701 third-level values; the 96 parent-scoped `Other` choices required and retained a custom name.
- Focused local checks passed in isolated SQLite databases: 51 checks across catalog, routes, bridge, database selection, message-migration regression, and Finder suites. No checked-in or production database was targeted.
- The end-to-end flow runs: migration → Create → persisted Item → Pending → Admin approval → Explore L1/L2/L3 filters → Details → Edit.
- Route examples include School Buses, Popcorn Machines, a non-Digital `Other` custom value, a two-level Housing branch, Digital Accounts → Amazon Prime Video, an old untyped Cars listing, and an L1-only legacy `vehicle` listing viewed under canonical Vehicles, retained after a validation-error re-render, and saved unchanged after Edit.
- Create and Explore are asserted to render seeded zero-listing categories.
- Jinja templates were parsed successfully after the changes.

Not executed: a live browser/device visual run at 320/360/375/390/430 px, a physical iPhone test, deployment, or any production mutation. The browser surfaces available in this workspace were Render/production tabs only, so they were deliberately not opened under this local-only scope. The new in-form search controls are native, keyboard-accessible `<input type="search">` filters and are shown only when a select has more than 12 choices; they were covered through rendered route HTML, not a live device screenshot.

## H. Local operator instructions

1. Review the uncommitted local changes and the baseline/report files. Do not stage, commit, push, deploy, or point a local process at a production `DATABASE_URL` as part of this task.
2. On an isolated development or staging database only, inspect the existing `categories` and `subcategories` rows for case-insensitive duplicates before applying the migration. Resolve ambiguity manually; the migration intentionally aborts instead of merging it.
3. With an explicitly isolated database URL, run `alembic upgrade head` and confirm `merge_taxonomy_20261004` is the resulting local/staging revision. For the observed production base, use the separate scoped bridge runbook rather than `head`.
4. Repeat the focused test commands from the test evidence section using an isolated environment.
5. Before any separate production rollout, take an approved backup and perform a read-only inventory comparison. Production rollout is outside this task and was not attempted.

The production-only sequence is documented in [render_taxonomy_bridge_runbook.md](render_taxonomy_bridge_runbook.md). No Git write command, Render deployment, production migration, production restart, or production reindex was performed.

## I. Out-of-scope observation

The focused test run emitted `python-dotenv could not parse statement starting at line 18` while reading the existing local `.env`. It did not expose a value and did not prevent the isolated taxonomy tests from passing. It is unrelated to taxonomy and was intentionally not changed.

The legacy Home rails still read `app/utils.py:CATEGORIES` through `app/main.py`; that is a separate older, two-level presentation list (`vehicle`, `housing`, and similar aliases). It is not used by Create, Edit, Admin, Explore, Search, or Finder, so it cannot hide or invalidate a new listing in the flow tested here. It was intentionally not changed by this Create/Explore-focused task; it should be consolidated separately if Home is expected to browse the complete expanded catalog.
