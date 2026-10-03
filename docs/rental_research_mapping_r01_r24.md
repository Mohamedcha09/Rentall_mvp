# Rental-research mapping: R01–R24

**Local planning artifact — 2026-10-03.** This maps the 179 supplied source
references from R01 through R24 to the *currently modified* central catalog in
`app/rental_catalog.py`. It does not write a database, create listings, or
assert local availability. `ADDED` means a canonical active catalog path is
present in the research extension; `EXISTING` means the exact concept was
already represented; `ALIAS_MAPPED` preserves a narrower/broader source label
without creating a duplicate; `KIT_COMPONENT_MAPPED` keeps a component with its
real kit; `RENTAL_MODE_MAPPED` represents an on-site/service mode rather than a
portable asset; and `REVIEW_REQUIRED` is deliberately not active.

The primary URLs are the research sources supplied with the request. Where the
entry is active, a listing still determines collection, delivery, operator,
compatibility, or long-term-rental terms; the taxonomy does not make those
claims.

## R01 — Concession machines (8)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R01-01 | Popcorn machine | ALIAS_MAPPED | Food & Concession Equipment → Popcorn Equipment → Popcorn Machines | Portable concession equipment; supplies remain separate consumables. | https://www.planitrentals.com/concession-machine-rentals |
| R01-02 | Cotton candy machine | ALIAS_MAPPED | Food & Concession Equipment → Frozen & Dessert Equipment → Cotton Candy Machines | Portable concession equipment. | https://www.planitrentals.com/concession-machine-rentals |
| R01-03 | Shaved ice machine | ADDED | Food & Concession Equipment → Frozen & Dessert Equipment → Shaved Ice Machines | Portable concession equipment. | https://www.planitrentals.com/concession-machine-rentals |
| R01-04 | Soft-serve ice cream machine | ALIAS_MAPPED | Food & Concession Equipment → Frozen & Dessert Equipment → Soft-Serve Machines | Portable/venue equipment; listing describes power and cleaning requirements. | https://www.planitrentals.com/concession-machine-rentals |
| R01-05 | Hot dog roller | ALIAS_MAPPED | Food & Concession Equipment → Hot Dog Equipment → Hot Dog Rollers | Portable concession equipment. | https://www.planitrentals.com/concession-machine-rentals |
| R01-06 | Slush machine | ALIAS_MAPPED | Food & Concession Equipment → Frozen & Dessert Equipment → Slush Machines | Portable concession equipment. | https://www.planitrentals.com/concession-machine-rentals |
| R01-07 | Chocolate fountain | ALIAS_MAPPED | Food & Concession Equipment → Frozen & Dessert Equipment → Chocolate Fountains | Portable event equipment; chocolate is not a rental asset. | https://www.planitrentals.com/concession-machine-rentals |
| R01-08 | Nacho cheese dispenser | ADDED | Food & Concession Equipment → Frozen & Dessert Equipment → Nacho Cheese Dispensers | Equipment only; cheese is consumable. | https://www.planitrentals.com/concession-machine-rentals |

## R02 — Donut and baking equipment (4)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R02-01 | Mini doughnut maker | ALIAS_MAPPED | Food & Concession Equipment → Donut Equipment → Donut Makers | Equipment only; ingredients and oil are consumables. | https://www.allenshire.co.uk/products/mini-doughnut-maker |
| R02-02 | Heated holding and proofing cabinet | ALIAS_MAPPED | Food & Concession Equipment → Commercial Kitchen Equipment → Hot Cupboards | Broader heated holding path; proofing capability belongs in listing details. | https://www.expohire.com/product/kn-war-hhpdc/heated-holding-proofing-display-cabinet-hire |
| R02-03 | Commercial gas deep fryer | ALIAS_MAPPED | Food & Concession Equipment → Cooking Equipment → Commercial Fryers | Gas type and installation requirements are attributes, not taxonomy children. | https://hiresocietysouthwest.com.au/collections/catering-equipment |
| R02-04 | Double bench fryer | ALIAS_MAPPED | Food & Concession Equipment → Cooking Equipment → Commercial Fryers | Bench/double configuration is listing detail. | https://hiresocietysouthwest.com.au/collections/catering-equipment |

## R03 — Commercial kitchen preparation (6)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R03-01 | Catering oven | ADDED | Food & Concession Equipment → Commercial Kitchen Equipment → Catering Ovens | Equipment hire; fuel/power and setup remain listing requirements. | https://www.platohire.co.uk/ |
| R03-02 | Hot cupboard | ADDED | Food & Concession Equipment → Commercial Kitchen Equipment → Hot Cupboards | Equipment hire. | https://www.platohire.co.uk/ |
| R03-03 | Commercial refrigerator | ADDED | Food & Concession Equipment → Commercial Kitchen Equipment → Commercial Refrigerators | Equipment hire; capacity is listing detail. | https://www.platohire.co.uk/ |
| R03-04 | Commercial freezer | ADDED | Food & Concession Equipment → Commercial Kitchen Equipment → Commercial Freezers | Equipment hire; capacity is listing detail. | https://www.platohire.co.uk/ |
| R03-05 | Barbecue equipment | ALIAS_MAPPED | Food & Concession Equipment → Cooking Equipment → Grills & Griddles | BBQ fuel/form factor remains a listing attribute. | https://www.platohire.co.uk/ |
| R03-06 | Preparation table | ADDED | Food & Concession Equipment → Commercial Kitchen Equipment → Preparation Tables | Equipment hire. | https://www.platohire.co.uk/ |

## R04 — Food and beverage serving (6)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R04-01 | Rectangular chafing dish | ADDED | Food & Concession Equipment → Serving & Beverage Equipment → Rectangular Chafing Dishes | Reusable serving equipment. | https://www.planitrentals.com/concession-machine-rentals |
| R04-02 | Round roll-top chafing dish | ADDED | Food & Concession Equipment → Serving & Beverage Equipment → Round Roll-Top Chafing Dishes | Reusable serving equipment. | https://www.planitrentals.com/concession-machine-rentals |
| R04-03 | Insulated beverage dispenser | ADDED | Food & Concession Equipment → Serving & Beverage Equipment → Insulated Beverage Dispensers | Reusable serving equipment. | https://www.planitrentals.com/concession-machine-rentals |
| R04-04 | Hot chocolate urn | ADDED | Food & Concession Equipment → Serving & Beverage Equipment → Hot Chocolate Urns | Reusable serving equipment. | https://www.planitrentals.com/concession-machine-rentals |
| R04-05 | Beverage dispenser | ALIAS_MAPPED | Food & Concession Equipment → Serving & Beverage Equipment → Beverage Dispensers | Canonical plural path covers container form factor. | https://www.planitrentals.com/concession-machine-rentals |
| R04-06 | Beverage cooling trough | ADDED | Food & Concession Equipment → Serving & Beverage Equipment → Beverage Cooling Troughs | Reusable serving equipment. | https://www.planitrentals.com/concession-machine-rentals |

## R05 — Tableware and linen (8)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R05-01 | Dinner plates | ADDED | Events & Production Equipment → Tableware & Linen → Dinner Plates | Reusable tableware only. | https://www.platohire.co.uk/ |
| R05-02 | Glassware | ADDED | Events & Production Equipment → Tableware & Linen → Glassware | Reusable glassware only. | https://www.platohire.co.uk/ |
| R05-03 | Cutlery sets | ADDED | Events & Production Equipment → Tableware & Linen → Cutlery Sets | Reusable tableware only. | https://www.platohire.co.uk/ |
| R05-04 | Canape serving dishes | ADDED | Events & Production Equipment → Tableware & Linen → Canape Serving Dishes | Reusable serving equipment. | https://www.platohire.co.uk/ |
| R05-05 | Pastry and serving cutlery | ADDED | Events & Production Equipment → Tableware & Linen → Pastry & Serving Cutlery | Reusable serving equipment. | https://www.platohire.co.uk/ |
| R05-06 | Table linen | ADDED | Events & Production Equipment → Tableware & Linen → Table Linen | Reusable textile inventory; disposable linen excluded. | https://www.platohire.co.uk/ |
| R05-07 | Service linen | ADDED | Events & Production Equipment → Tableware & Linen → Service Linen | Reusable textile inventory; disposable linen excluded. | https://www.platohire.co.uk/ |
| R05-08 | Chair sashes | ADDED | Events & Production Equipment → Tableware & Linen → Chair Sashes | Reusable event textile. | https://www.platohire.co.uk/ |

## R06 — Packaging equipment (2)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R06-01 | Vacuum packaging machine | ADDED | Warehousing & Logistics → Packaging & Labeling → Vacuum Packaging Machines | Equipment rental; bags remain consumables. | https://vacpac.com.au/rentals/ |
| R06-02 | Pallet stretch wrapper | ADDED | Warehousing & Logistics → Packaging & Labeling → Pallet Stretch Wrappers | May be long-term program; duration/pricing are listing terms. | https://www.rentawrapper.co.uk/ |

## R07 — Sewing and textile workstations (6)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R07-01 | Sewing machine | ALIAS_MAPPED | Hobbies & Creative Equipment → Sewing & Textile → Sewing Machines | Can be portable or an on-site offer; listing declares mode. | https://espacefabrik.com/en/products/location-de-machine ; https://empiremakespace.com/collections/studio-rental ; https://www.trianglesewing.com/online-store/SEWING-MACHINE-RENTAL-p700972559 |
| R07-02 | Overlocker or serger | ALIAS_MAPPED | Hobbies & Creative Equipment → Sewing & Textile → Serger Machines | “Overlocker” maps to the canonical serger label. | https://espacefabrik.com/en/products/location-de-machine ; https://empiremakespace.com/collections/studio-rental ; https://www.trianglesewing.com/online-store/SEWING-MACHINE-RENTAL-p700972559 |
| R07-03 | Coverstitch machine | ADDED | Hobbies & Creative Equipment → Sewing & Textile → Coverstitch Machines | Portable/on-site mode is listing-specific. | https://espacefabrik.com/en/products/location-de-machine ; https://empiremakespace.com/collections/studio-rental ; https://www.trianglesewing.com/online-store/SEWING-MACHINE-RENTAL-p700972559 |
| R07-04 | Fabric cutting table | ADDED | Hobbies & Creative Equipment → Sewing & Textile → Fabric Cutting Tables | May be an in-studio workstation; listing declares mode. | https://espacefabrik.com/en/products/location-de-machine ; https://empiremakespace.com/collections/studio-rental ; https://www.trianglesewing.com/online-store/SEWING-MACHINE-RENTAL-p700972559 |
| R07-05 | Ironing station | ADDED | Hobbies & Creative Equipment → Sewing & Textile → Ironing Stations | May be an in-studio workstation; listing declares mode. | https://espacefabrik.com/en/products/location-de-machine ; https://empiremakespace.com/collections/studio-rental ; https://www.trianglesewing.com/online-store/SEWING-MACHINE-RENTAL-p700972559 |
| R07-06 | Fabric die-cutting machine | ADDED | Hobbies & Creative Equipment → Sewing & Textile → Fabric Die-Cutting Machines | Portable/on-site mode is listing-specific. | https://espacefabrik.com/en/products/location-de-machine ; https://empiremakespace.com/collections/studio-rental ; https://www.trianglesewing.com/online-store/SEWING-MACHINE-RENTAL-p700972559 |

## R08 — Site textile tool (1)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R08-01 | Portable geotextile sewing machine | ADDED | Construction & Industrial Equipment → Geotextile & Site Textile Tools → Portable Geotextile Sewing Machines | Professional equipment; operator/safety terms stay on the listing. | https://boutiquepro.ghlinc.com/shop/195-120-011000-newlong-np-7h-sewing-machine-rental-day-5859 |

## R09 — On-site heat press (1)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R09-01 | Heat press workstation | RENTAL_MODE_MAPPED | Spaces & Studios → Workshops & Maker Spaces → Heat-Press Workstations | Source supports booked space/time use, not a claim of portable home-machine rental. | https://www.herdcreations.com/products/heat-press-space-rental |

## R10 — Badge-making kit (3)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R10-01 | Button badge press kit | ADDED | Hobbies & Creative Equipment → Arts & Crafts → Button Badge Press Kits | Canonical rental unit is the reusable kit. | https://chibuttons.com/button-machines-moulds-cutters-rental-page ; https://peoplepowerpress.org/collections/button-machine-rentals |
| R10-02 | Badge-making mold | KIT_COMPONENT_MAPPED | Hobbies & Creative Equipment → Arts & Crafts → Button Badge Press Kits | Mold is represented as a kit component; blank badges are consumables. | https://chibuttons.com/button-machines-moulds-cutters-rental-page ; https://peoplepowerpress.org/collections/button-machine-rentals |
| R10-03 | Graphic circle cutter | KIT_COMPONENT_MAPPED | Hobbies & Creative Equipment → Arts & Crafts → Button Badge Press Kits | Cutter is represented as a kit component; no unsupported promise of separate hire. | https://chibuttons.com/button-machines-moulds-cutters-rental-page ; https://peoplepowerpress.org/collections/button-machine-rentals |

## R11 — Pottery (1)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R11-01 | Pottery wheel | ALIAS_MAPPED | Hobbies & Creative Equipment → Arts & Crafts → Pottery Wheels | Singular source label maps to existing canonical plural. | https://www.sunsoulbowls.com/services/p/pottery-wheel-rental |

## R12 — Industrial additive manufacturing (3)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R12-01 | Industrial FDM or FFF 3D printer | REVIEW_REQUIRED | Not active: industrial installed/long-term program needs platform, delivery, training, and insurance review. | Source describes a specialist program rather than ordinary self-service hire. | https://agile-manufacturing.com/3d-printer-rental-program/ |
| R12-02 | Industrial SLA 3D printer | REVIEW_REQUIRED | Not active: industrial installed/long-term program needs platform, delivery, training, and insurance review. | Source describes a specialist program rather than ordinary self-service hire. | https://agile-manufacturing.com/3d-printer-rental-program/ |
| R12-03 | Industrial SLS 3D printer | REVIEW_REQUIRED | Not active: industrial installed/long-term program needs platform, delivery, training, and insurance review. | Source describes a specialist program rather than ordinary self-service hire. | https://agile-manufacturing.com/3d-printer-rental-program/ |

## R13 — Automotive workshop tools (16)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R13-01 | Battery booster | ADDED | Tools & Equipment → Automotive Workshop Tools → Battery Boosters | Equipment hire. | https://www.wbrental.com/automotive.html |
| R13-02 | Battery tester | ADDED | Tools & Equipment → Automotive Workshop Tools → Battery Testers | Equipment hire. | https://www.wbrental.com/automotive.html |
| R13-03 | Battery charger | ADDED | Tools & Equipment → Automotive Workshop Tools → Battery Chargers | Equipment hire. | https://www.wbrental.com/automotive.html |
| R13-04 | Cooling-system pressure tester | ADDED | Tools & Equipment → Automotive Workshop Tools → Cooling-System Pressure Testers | Equipment hire. | https://www.wbrental.com/automotive.html |
| R13-05 | Automotive inspection borescope | ADDED | Tools & Equipment → Automotive Workshop Tools → Automotive Inspection Borescopes | Equipment hire. | https://www.wbrental.com/automotive.html |
| R13-06 | Hydraulic body repair kit | ADDED | Tools & Equipment → Automotive Workshop Tools → Hydraulic Body Repair Kits | Canonical reusable kit. | https://www.wbrental.com/automotive.html |
| R13-07 | Vibratory tumbler | ADDED | Tools & Equipment → Automotive Workshop Tools → Vibratory Tumblers | Equipment hire. | https://www.wbrental.com/automotive.html |
| R13-08 | Ultrasonic cleaner | ADDED | Tools & Equipment → Automotive Workshop Tools → Ultrasonic Cleaners | Equipment hire. | https://www.wbrental.com/automotive.html |
| R13-09 | Large socket and ratchet set | ADDED | Tools & Equipment → Automotive Workshop Tools → Large Socket & Ratchet Sets | Canonical reusable kit. | https://www.wbrental.com/automotive.html |
| R13-10 | Engine stand | ADDED | Tools & Equipment → Automotive Workshop Tools → Engine Stands | Equipment hire. | https://www.wbrental.com/automotive.html |
| R13-11 | Jack stands | ADDED | Tools & Equipment → Automotive Workshop Tools → Jack Stands | Equipment hire. | https://www.wbrental.com/automotive.html |
| R13-12 | Transmission jack | ADDED | Tools & Equipment → Automotive Workshop Tools → Transmission Jacks | Equipment hire. | https://www.wbrental.com/automotive.html |
| R13-13 | Impact wrench | ADDED | Tools & Equipment → Automotive Workshop Tools → Impact Wrenches | Equipment hire. | https://www.wbrental.com/automotive.html |
| R13-14 | Torque wrench | ADDED | Tools & Equipment → Automotive Workshop Tools → Torque Wrenches | Equipment hire. | https://www.wbrental.com/automotive.html |
| R13-15 | Tailpipe expander | ADDED | Tools & Equipment → Automotive Workshop Tools → Tailpipe Expanders | Equipment hire. | https://www.wbrental.com/automotive.html |
| R13-16 | Valve spring compressor | ADDED | Tools & Equipment → Automotive Workshop Tools → Valve Spring Compressors | Equipment hire. | https://www.wbrental.com/automotive.html |

## R14 — Portable power tools (13)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R14-01 | Angle grinder | ADDED | Tools & Equipment → Power Tools → Angle Grinders | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/ ; https://www.loutec.com/en/location-outils-equipements/electric-tools/ |
| R14-02 | Belt sander | ADDED | Tools & Equipment → Power Tools → Belt Sanders | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/ ; https://www.loutec.com/en/location-outils-equipements/electric-tools/ |
| R14-03 | Orbital sander | ADDED | Tools & Equipment → Power Tools → Orbital Sanders | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/ ; https://www.loutec.com/en/location-outils-equipements/electric-tools/ |
| R14-04 | Circular saw | ADDED | Tools & Equipment → Power Tools → Circular Saws | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/ ; https://www.loutec.com/en/location-outils-equipements/electric-tools/ |
| R14-05 | Miter saw | ADDED | Tools & Equipment → Power Tools → Miter Saws | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/ ; https://www.loutec.com/en/location-outils-equipements/electric-tools/ |
| R14-06 | Band saw | ADDED | Tools & Equipment → Power Tools → Band Saws | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/ ; https://www.loutec.com/en/location-outils-equipements/electric-tools/ |
| R14-07 | Reciprocating saw | ADDED | Tools & Equipment → Power Tools → Reciprocating Saws | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/ ; https://www.loutec.com/en/location-outils-equipements/electric-tools/ |
| R14-08 | Table saw | ADDED | Tools & Equipment → Power Tools → Table Saws | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/ ; https://www.loutec.com/en/location-outils-equipements/electric-tools/ |
| R14-09 | Electric planer | ADDED | Tools & Equipment → Power Tools → Electric Planers | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/ ; https://www.loutec.com/en/location-outils-equipements/electric-tools/ |
| R14-10 | Router | ADDED | Tools & Equipment → Power Tools → Routers | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/ ; https://www.loutec.com/en/location-outils-equipements/electric-tools/ |
| R14-11 | Magnetic drill | ADDED | Tools & Equipment → Power Tools → Magnetic Drills | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/ ; https://www.loutec.com/en/location-outils-equipements/electric-tools/ |
| R14-12 | Heat gun | ADDED | Tools & Equipment → Power Tools → Heat Guns | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/ ; https://www.loutec.com/en/location-outils-equipements/electric-tools/ |
| R14-13 | Metal shear or nibbler | ADDED | Tools & Equipment → Power Tools → Metal Shears & Nibblers | Canonical combined type retains both source terms. | https://www.sunbeltrentals.com/equipment-rental/ ; https://www.loutec.com/en/location-outils-equipements/electric-tools/ |

## R15 — Floor installation and removal (10)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R15-01 | Drum floor sander | ADDED | Tools & Equipment → Floor Installation & Removal → Drum Floor Sanders | Equipment hire. | https://www.homedepot.ca/tool-and-vehicle-rental/flooring-tool-rental ; https://www.jconnellyrental.com/en/rental/specialized-tools/flooring-tools/ ; https://www.bear-rental.com/product/flooring-tools/hardwood/dewalt-2-in-1-flooring-tool-rental/ |
| R15-02 | Orbital floor sander | ADDED | Tools & Equipment → Floor Installation & Removal → Orbital Floor Sanders | Equipment hire. | https://www.homedepot.ca/tool-and-vehicle-rental/flooring-tool-rental ; https://www.jconnellyrental.com/en/rental/specialized-tools/flooring-tools/ ; https://www.bear-rental.com/product/flooring-tools/hardwood/dewalt-2-in-1-flooring-tool-rental/ |
| R15-03 | Floor edge sander | ADDED | Tools & Equipment → Floor Installation & Removal → Floor Edge Sanders | Equipment hire. | https://www.homedepot.ca/tool-and-vehicle-rental/flooring-tool-rental ; https://www.jconnellyrental.com/en/rental/specialized-tools/flooring-tools/ ; https://www.bear-rental.com/product/flooring-tools/hardwood/dewalt-2-in-1-flooring-tool-rental/ |
| R15-04 | Carpet knee kicker | ADDED | Tools & Equipment → Floor Installation & Removal → Carpet Knee Kickers | Equipment hire. | https://www.homedepot.ca/tool-and-vehicle-rental/flooring-tool-rental ; https://www.jconnellyrental.com/en/rental/specialized-tools/flooring-tools/ ; https://www.bear-rental.com/product/flooring-tools/hardwood/dewalt-2-in-1-flooring-tool-rental/ |
| R15-05 | Floor stripping machine | ADDED | Tools & Equipment → Floor Installation & Removal → Floor Stripping Machines | Equipment hire. | https://www.homedepot.ca/tool-and-vehicle-rental/flooring-tool-rental ; https://www.jconnellyrental.com/en/rental/specialized-tools/flooring-tools/ ; https://www.bear-rental.com/product/flooring-tools/hardwood/dewalt-2-in-1-flooring-tool-rental/ |
| R15-06 | Tile cutter | ADDED | Tools & Equipment → Floor Installation & Removal → Tile Cutters | Equipment hire. | https://www.homedepot.ca/tool-and-vehicle-rental/flooring-tool-rental ; https://www.jconnellyrental.com/en/rental/specialized-tools/flooring-tools/ ; https://www.bear-rental.com/product/flooring-tools/hardwood/dewalt-2-in-1-flooring-tool-rental/ |
| R15-07 | Vinyl flooring cutter | ADDED | Tools & Equipment → Floor Installation & Removal → Vinyl Flooring Cutters | Equipment hire. | https://www.homedepot.ca/tool-and-vehicle-rental/flooring-tool-rental ; https://www.jconnellyrental.com/en/rental/specialized-tools/flooring-tools/ ; https://www.bear-rental.com/product/flooring-tools/hardwood/dewalt-2-in-1-flooring-tool-rental/ |
| R15-08 | Hardwood floor nailer | ADDED | Tools & Equipment → Floor Installation & Removal → Hardwood Floor Nailers | Equipment hire. | https://www.homedepot.ca/tool-and-vehicle-rental/flooring-tool-rental ; https://www.jconnellyrental.com/en/rental/specialized-tools/flooring-tools/ ; https://www.bear-rental.com/product/flooring-tools/hardwood/dewalt-2-in-1-flooring-tool-rental/ |
| R15-09 | Concrete floor grinder | ADDED | Tools & Equipment → Floor Installation & Removal → Concrete Floor Grinders | Equipment hire. | https://www.homedepot.ca/tool-and-vehicle-rental/flooring-tool-rental ; https://www.jconnellyrental.com/en/rental/specialized-tools/flooring-tools/ ; https://www.bear-rental.com/product/flooring-tools/hardwood/dewalt-2-in-1-flooring-tool-rental/ |
| R15-10 | Dust extractor | ADDED | Tools & Equipment → Floor Installation & Removal → Dust Extractors | Equipment hire. | https://www.homedepot.ca/tool-and-vehicle-rental/flooring-tool-rental ; https://www.jconnellyrental.com/en/rental/specialized-tools/flooring-tools/ ; https://www.bear-rental.com/product/flooring-tools/hardwood/dewalt-2-in-1-flooring-tool-rental/ |

## R16 — Pipe and plumbing tools (10)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R16-01 | Pipe bender | ADDED | Tools & Equipment → Plumbing & Pipe Tools → Pipe Benders | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/plumbing-pipe-conduit ; https://www.sunbeltrentals.com/equipment-rental/general-construction-tools/pipe-freezing-tool-ridgid-sf2500-rental/0740525/ |
| R16-02 | Pipe cutter | ADDED | Tools & Equipment → Plumbing & Pipe Tools → Pipe Cutters | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/plumbing-pipe-conduit ; https://www.sunbeltrentals.com/equipment-rental/general-construction-tools/pipe-freezing-tool-ridgid-sf2500-rental/0740525/ |
| R16-03 | Pipe threading machine | ADDED | Tools & Equipment → Plumbing & Pipe Tools → Pipe Threading Machines | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/plumbing-pipe-conduit ; https://www.sunbeltrentals.com/equipment-rental/general-construction-tools/pipe-freezing-tool-ridgid-sf2500-rental/0740525/ |
| R16-04 | Threading dies | ADDED | Tools & Equipment → Plumbing & Pipe Tools → Threading Dies | May be provided as attachment/kit component; listing declares separate availability. | https://www.unitedrentals.com/marketplace/equipment/plumbing-pipe-conduit ; https://www.sunbeltrentals.com/equipment-rental/general-construction-tools/pipe-freezing-tool-ridgid-sf2500-rental/0740525/ |
| R16-05 | Pipe oiler | ADDED | Tools & Equipment → Plumbing & Pipe Tools → Pipe Oilers | May be provided as attachment/kit component; listing declares separate availability. | https://www.unitedrentals.com/marketplace/equipment/plumbing-pipe-conduit ; https://www.sunbeltrentals.com/equipment-rental/general-construction-tools/pipe-freezing-tool-ridgid-sf2500-rental/0740525/ |
| R16-06 | Pipe stand | ADDED | Tools & Equipment → Plumbing & Pipe Tools → Pipe Stands | May be provided as attachment/kit component; listing declares separate availability. | https://www.unitedrentals.com/marketplace/equipment/plumbing-pipe-conduit ; https://www.sunbeltrentals.com/equipment-rental/general-construction-tools/pipe-freezing-tool-ridgid-sf2500-rental/0740525/ |
| R16-07 | Pipe crimping tool | ADDED | Tools & Equipment → Plumbing & Pipe Tools → Pipe Crimping Tools | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/plumbing-pipe-conduit ; https://www.sunbeltrentals.com/equipment-rental/general-construction-tools/pipe-freezing-tool-ridgid-sf2500-rental/0740525/ |
| R16-08 | Flange spreader | ADDED | Tools & Equipment → Plumbing & Pipe Tools → Flange Spreaders | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/plumbing-pipe-conduit ; https://www.sunbeltrentals.com/equipment-rental/general-construction-tools/pipe-freezing-tool-ridgid-sf2500-rental/0740525/ |
| R16-09 | Sewer inspection camera | ADDED | Tools & Equipment → Plumbing & Pipe Tools → Sewer Inspection Cameras | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/plumbing-pipe-conduit ; https://www.sunbeltrentals.com/equipment-rental/general-construction-tools/pipe-freezing-tool-ridgid-sf2500-rental/0740525/ |
| R16-10 | Pipe freezing machine | ADDED | Tools & Equipment → Plumbing & Pipe Tools → Pipe Freezing Machines | Equipment hire; site and safety details remain listing-specific. | https://www.unitedrentals.com/marketplace/equipment/plumbing-pipe-conduit ; https://www.sunbeltrentals.com/equipment-rental/general-construction-tools/pipe-freezing-tool-ridgid-sf2500-rental/0740525/ |

## R17 — Welding and pipe fabrication (5)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R17-01 | Welding power source | ADDED | Construction & Industrial Equipment → Welding & Fabrication → Welding Power Sources | Professional equipment; operator/process requirements remain listing terms. | https://canadaweldingsupply.com/collections/rental-equipment ; https://orbitalum.com/en-ca/rentals/ |
| R17-02 | Orbital welding system | ADDED | Construction & Industrial Equipment → Welding & Fabrication → Orbital Welding Systems | Professional equipment; operator/process requirements remain listing terms. | https://canadaweldingsupply.com/collections/rental-equipment ; https://orbitalum.com/en-ca/rentals/ |
| R17-03 | Tube cutting machine | ADDED | Construction & Industrial Equipment → Welding & Fabrication → Tube Cutting Machines | Professional equipment. | https://canadaweldingsupply.com/collections/rental-equipment ; https://orbitalum.com/en-ca/rentals/ |
| R17-04 | Pipe cutting machine | ADDED | Construction & Industrial Equipment → Welding & Fabrication → Pipe Cutting Machines | Professional equipment. | https://canadaweldingsupply.com/collections/rental-equipment ; https://orbitalum.com/en-ca/rentals/ |
| R17-05 | Tube facing machine | ADDED | Construction & Industrial Equipment → Welding & Fabrication → Tube Facing Machines | Professional equipment. | https://canadaweldingsupply.com/collections/rental-equipment ; https://orbitalum.com/en-ca/rentals/ |

## R18 — Hydraulic maintenance tools (10)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R18-01 | Hydraulic torque wrench | ADDED | Construction & Industrial Equipment → Hydraulic Maintenance Tools → Hydraulic Torque Wrenches | Capacity/drive compatibility remain listing details. | https://www.sunbeltrentals.com/equipment-rental/ |
| R18-02 | Low-height hydraulic cylinder | ADDED | Construction & Industrial Equipment → Hydraulic Maintenance Tools → Low-Height Hydraulic Cylinders | Capacity/drive compatibility remain listing details. | https://www.sunbeltrentals.com/equipment-rental/ |
| R18-03 | Hollow-plunger hydraulic cylinder | ADDED | Construction & Industrial Equipment → Hydraulic Maintenance Tools → Hollow-Plunger Hydraulic Cylinders | Capacity/drive compatibility remain listing details. | https://www.sunbeltrentals.com/equipment-rental/ |
| R18-04 | Lock-nut hydraulic cylinder | ADDED | Construction & Industrial Equipment → Hydraulic Maintenance Tools → Lock-Nut Hydraulic Cylinders | Capacity/drive compatibility remain listing details. | https://www.sunbeltrentals.com/equipment-rental/ |
| R18-05 | Pancake hydraulic cylinder | ADDED | Construction & Industrial Equipment → Hydraulic Maintenance Tools → Pancake Hydraulic Cylinders | Capacity/drive compatibility remain listing details. | https://www.sunbeltrentals.com/equipment-rental/ |
| R18-06 | Hydraulic hand pump | ADDED | Construction & Industrial Equipment → Hydraulic Maintenance Tools → Hydraulic Hand Pumps | Capacity/drive compatibility remain listing details. | https://www.sunbeltrentals.com/equipment-rental/ |
| R18-07 | Hydraulic electric pump | ADDED | Construction & Industrial Equipment → Hydraulic Maintenance Tools → Hydraulic Electric Pumps | Capacity/drive compatibility remain listing details. | https://www.sunbeltrentals.com/equipment-rental/ |
| R18-08 | Hydraulic nut splitter | ADDED | Construction & Industrial Equipment → Hydraulic Maintenance Tools → Hydraulic Nut Splitters | Professional equipment. | https://www.sunbeltrentals.com/equipment-rental/ |
| R18-09 | Hydraulic punch | ADDED | Construction & Industrial Equipment → Hydraulic Maintenance Tools → Hydraulic Punches | Professional equipment. | https://www.sunbeltrentals.com/equipment-rental/ |
| R18-10 | Hydraulic cutterhead | ADDED | Construction & Industrial Equipment → Hydraulic Maintenance Tools → Hydraulic Cutterheads | Professional equipment. | https://www.sunbeltrentals.com/equipment-rental/ |

## R19 — Concrete and masonry (15)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R19-01 | Concrete mixer | ALIAS_MAPPED | Construction & Industrial Equipment → Concrete & Masonry → Concrete Mixers | Singular source label maps to existing canonical plural. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |
| R19-02 | Mortar mixer | ADDED | Construction & Industrial Equipment → Concrete & Masonry → Mortar Mixers | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |
| R19-03 | Concrete vibrator | ADDED | Construction & Industrial Equipment → Concrete & Masonry → Concrete Vibrators | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |
| R19-04 | Concrete buggy | ADDED | Construction & Industrial Equipment → Concrete & Masonry → Concrete Buggies | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |
| R19-05 | Concrete bucket | ADDED | Construction & Industrial Equipment → Concrete & Masonry → Concrete Buckets | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |
| R19-06 | Power trowel | ALIAS_MAPPED | Construction & Industrial Equipment → Concrete & Masonry → Trowels | Existing broad canonical type; powered operation belongs in listing details. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |
| R19-07 | Concrete floor saw | ADDED | Construction & Industrial Equipment → Concrete & Masonry → Concrete Floor Saws | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |
| R19-08 | Diamond core drill | ADDED | Construction & Industrial Equipment → Concrete & Masonry → Diamond Core Drills | Equipment hire; bit size is listing detail. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |
| R19-09 | Masonry saw | ADDED | Construction & Industrial Equipment → Concrete & Masonry → Masonry Saws | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |
| R19-10 | Tile saw | ADDED | Construction & Industrial Equipment → Concrete & Masonry → Tile Saws | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |
| R19-11 | Rebar cutter | ADDED | Construction & Industrial Equipment → Concrete & Masonry → Rebar Cutters | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |
| R19-12 | Rebar bender | ADDED | Construction & Industrial Equipment → Concrete & Masonry → Rebar Benders | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |
| R19-13 | Rebar tying tool | ADDED | Construction & Industrial Equipment → Concrete & Masonry → Rebar Tying Tools | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |
| R19-14 | Concrete scarifier | ADDED | Construction & Industrial Equipment → Concrete & Masonry → Concrete Scarifiers | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |
| R19-15 | Portable shot blaster | ADDED | Construction & Industrial Equipment → Concrete & Masonry → Portable Shot Blasters | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/concrete-and-masonry/ ; https://www.loutec.com/en/equipment-rental/concrete/ |

## R20 — Floor and surface cleaning (10)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R20-01 | Carpet extractor | ADDED | Tools & Equipment → Cleaning & Restoration Equipment → Carpet Extractors | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/surface-preparation |
| R20-02 | Floor polisher | ADDED | Tools & Equipment → Cleaning & Restoration Equipment → Floor Polishers | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/surface-preparation |
| R20-03 | Walk-behind scrubber | ADDED | Tools & Equipment → Cleaning & Restoration Equipment → Walk-Behind Scrubbers | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/surface-preparation |
| R20-04 | Ride-on scrubber | ADDED | Tools & Equipment → Cleaning & Restoration Equipment → Ride-On Scrubbers | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/surface-preparation |
| R20-05 | Handheld sweeper | ADDED | Tools & Equipment → Cleaning & Restoration Equipment → Handheld Sweepers | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/surface-preparation |
| R20-06 | Walk-behind sweeper | ADDED | Tools & Equipment → Cleaning & Restoration Equipment → Walk-Behind Sweepers | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/surface-preparation |
| R20-07 | Ride-on sweeper | ADDED | Tools & Equipment → Cleaning & Restoration Equipment → Ride-On Sweepers | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/surface-preparation |
| R20-08 | Wet and dry vacuum | ADDED | Tools & Equipment → Cleaning & Restoration Equipment → Wet & Dry Vacuums | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/surface-preparation |
| R20-09 | Hot-water pressure washer | ADDED | Tools & Equipment → Cleaning & Restoration Equipment → Hot-Water Pressure Washers | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/surface-preparation |
| R20-10 | Cold-water pressure washer | ADDED | Tools & Equipment → Cleaning & Restoration Equipment → Cold-Water Pressure Washers | Equipment hire. | https://www.unitedrentals.com/marketplace/equipment/surface-preparation |

## R21 — Climate control and drying (13)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R21-01 | Refrigerant dehumidifier | ADDED | Temporary Infrastructure & Site Services → Drying & Air Quality → Refrigerant Dehumidifiers | Equipment hire; capacity and electrical conditions stay on listing. | https://www.sunbeltrentals.com/equipment-rental/heating-cooling-air-management/ |
| R21-02 | Desiccant dehumidifier | ADDED | Temporary Infrastructure & Site Services → Drying & Air Quality → Desiccant Dehumidifiers | Equipment hire; capacity and electrical conditions stay on listing. | https://www.sunbeltrentals.com/equipment-rental/heating-cooling-air-management/ |
| R21-03 | Portable air scrubber | ALIAS_MAPPED | Temporary Infrastructure & Site Services → Drying & Air Quality → Air Scrubbers | Existing canonical type covers the portable form factor. | https://www.sunbeltrentals.com/equipment-rental/heating-cooling-air-management/ |
| R21-04 | Carpet dryer or air mover | ADDED | Temporary Infrastructure & Site Services → Drying & Air Quality → Carpet Dryers & Air Movers | Canonical combined equipment type. | https://www.sunbeltrentals.com/equipment-rental/heating-cooling-air-management/ |
| R21-05 | High-volume fan | ADDED | Temporary Infrastructure & Site Services → Drying & Air Quality → High-Volume Fans | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/heating-cooling-air-management/ |
| R21-06 | Spot cooler | ADDED | Temporary Infrastructure & Site Services → Climate Control → Spot Coolers | Equipment hire. | https://www.sunbeltrentals.com/equipment-rental/heating-cooling-air-management/ |
| R21-07 | Portable air conditioner | ALIAS_MAPPED | Temporary Infrastructure & Site Services → Climate Control → Portable Air Conditioners | Singular source label maps to existing canonical plural. | https://www.sunbeltrentals.com/equipment-rental/heating-cooling-air-management/ |
| R21-08 | Industrial chiller | ADDED | Temporary Infrastructure & Site Services → Climate Control → Industrial Chillers | Equipment hire; connection and site suitability remain listing details. | https://www.sunbeltrentals.com/equipment-rental/heating-cooling-air-management/ |
| R21-09 | Cooling tower | ADDED | Temporary Infrastructure & Site Services → Climate Control → Cooling Towers | Equipment hire; connection and site suitability remain listing details. | https://www.sunbeltrentals.com/equipment-rental/heating-cooling-air-management/ |
| R21-10 | Air handler | ALIAS_MAPPED | Temporary Infrastructure & Site Services → Climate Control → Air Handlers | Singular source label maps to existing canonical plural. | https://www.sunbeltrentals.com/equipment-rental/heating-cooling-air-management/ |
| R21-11 | Electric heater | ADDED | Temporary Infrastructure & Site Services → Climate Control → Electric Heaters | Equipment hire; power/site conditions remain listing details. | https://www.sunbeltrentals.com/equipment-rental/heating-cooling-air-management/ |
| R21-12 | Indirect-fired heater | ADDED | Temporary Infrastructure & Site Services → Climate Control → Indirect-Fired Heaters | Equipment hire; fuel/site conditions remain listing details. | https://www.sunbeltrentals.com/equipment-rental/heating-cooling-air-management/ |
| R21-13 | Ground heater | ADDED | Temporary Infrastructure & Site Services → Climate Control → Ground Heaters | Equipment hire; site conditions remain listing details. | https://www.sunbeltrentals.com/equipment-rental/heating-cooling-air-management/ |

## R22 — Temporary power (10)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R22-01 | Portable generator | ALIAS_MAPPED | Temporary Infrastructure & Site Services → Power Generation → Generators | Portability, output, and fuel are listing attributes. | https://www.unitedrentals.com/marketplace/equipment/power-generation-equipment |
| R22-02 | Diesel generator | ALIAS_MAPPED | Temporary Infrastructure & Site Services → Power Generation → Generators | Fuel is an attribute, not a separate type. | https://www.unitedrentals.com/marketplace/equipment/power-generation-equipment |
| R22-03 | Natural-gas generator | ALIAS_MAPPED | Temporary Infrastructure & Site Services → Power Generation → Generators | Fuel is an attribute, not a separate type. | https://www.unitedrentals.com/marketplace/equipment/power-generation-equipment |
| R22-04 | Battery energy storage system | ALIAS_MAPPED | Temporary Infrastructure & Site Services → Power Generation → Battery Storage | Canonical label avoids duplicate wording. | https://www.unitedrentals.com/marketplace/equipment/power-generation-equipment |
| R22-05 | Power distribution panel | ALIAS_MAPPED | Temporary Infrastructure & Site Services → Power Generation → Power Distribution Panels | Singular source label maps to existing canonical plural. | https://www.unitedrentals.com/marketplace/equipment/power-generation-equipment |
| R22-06 | Transfer switch | ADDED | Temporary Infrastructure & Site Services → Power Generation → Transfer Switches | Electrical compatibility and installation are listing requirements. | https://www.unitedrentals.com/marketplace/equipment/power-generation-equipment |
| R22-07 | Transformer | ADDED | Temporary Infrastructure & Site Services → Power Generation → Transformers | Electrical compatibility and installation are listing requirements. | https://www.unitedrentals.com/marketplace/equipment/power-generation-equipment |
| R22-08 | Temporary power cable | ADDED | Temporary Infrastructure & Site Services → Power Generation → Temporary Power Cables | Connector/rating are listing attributes. | https://www.unitedrentals.com/marketplace/equipment/power-generation-equipment |
| R22-09 | Resistive load bank | ALIAS_MAPPED | Temporary Infrastructure & Site Services → Power Generation → Load Banks | Resistive/reactive behavior is a technical attribute. | https://www.unitedrentals.com/marketplace/equipment/power-generation-equipment |
| R22-10 | Resistive-reactive load bank | ALIAS_MAPPED | Temporary Infrastructure & Site Services → Power Generation → Load Banks | Resistive/reactive behavior is a technical attribute. | https://www.unitedrentals.com/marketplace/equipment/power-generation-equipment |

## R23 — Pumps, tanks, and fluid management (6)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R23-01 | Diaphragm pump | ADDED | Temporary Infrastructure & Site Services → Pumps & Water Management → Diaphragm Pumps | Fluid compatibility remains a listing restriction. | https://www.unitedrentals.com/marketplace/equipment/pumps-tanks-filtration |
| R23-02 | Trash or dewatering pump | ALIAS_MAPPED | Temporary Infrastructure & Site Services → Pumps & Water Management → Dewatering Pumps | “Trash” and dewatering capability map to the canonical dewatering type; fluid compatibility stays on listing. | https://www.unitedrentals.com/marketplace/equipment/pumps-tanks-filtration |
| R23-03 | Fluid storage tank | ADDED | Temporary Infrastructure & Site Services → Pumps & Water Management → Fluid Storage Tanks | Fluid compatibility remains a listing restriction. | https://www.unitedrentals.com/marketplace/equipment/pumps-tanks-filtration |
| R23-04 | Industrial water filtration equipment | ALIAS_MAPPED | Temporary Infrastructure & Site Services → Pumps & Water Management → Water Treatment Units | Canonical operational category; filtering configuration stays on listing. | https://www.unitedrentals.com/marketplace/equipment/pumps-tanks-filtration |
| R23-05 | Pump hose | KIT_COMPONENT_MAPPED | Temporary Infrastructure & Site Services → Pumps & Water Management | Hose is an attachment to its compatible pump, not a separate claimed hire type. | https://www.unitedrentals.com/marketplace/equipment/pumps-tanks-filtration |
| R23-06 | Pressure-washing hose | KIT_COMPONENT_MAPPED | Tools & Equipment → Cleaning & Restoration Equipment → Pressure Washers | Hose is an attachment to a compatible washer, not a separate claimed hire type. | https://www.unitedrentals.com/marketplace/equipment/pumps-tanks-filtration |

## R24 — Trench and ground protection (12)

| Ref | Source label | Final status | Canonical active path / review reason | Rental-mode or component note | Primary source URL(s) |
|---|---|---|---|---|---|
| R24-01 | Trench shield | ADDED | Construction & Industrial Equipment → Trench & Shoring → Trench Shields | Safety-critical equipment; installation/use conditions remain listing requirements. | https://www.unitedrentals.com/marketplace/equipment/trench-safety-shoring |
| R24-02 | Hydraulic shoring | ADDED | Construction & Industrial Equipment → Trench & Shoring → Hydraulic Shoring | Safety-critical equipment; installation/use conditions remain listing requirements. | https://www.unitedrentals.com/marketplace/equipment/trench-safety-shoring |
| R24-03 | Manhole brace | ADDED | Construction & Industrial Equipment → Trench & Shoring → Manhole Braces | Safety-critical equipment; installation/use conditions remain listing requirements. | https://www.unitedrentals.com/marketplace/equipment/trench-safety-shoring |
| R24-04 | Bedding box | ADDED | Construction & Industrial Equipment → Trench & Shoring → Bedding Boxes | Site equipment. | https://www.unitedrentals.com/marketplace/equipment/trench-safety-shoring |
| R24-05 | Ground protection mat | ADDED | Construction & Industrial Equipment → Trench & Shoring → Ground Protection Mats | Site equipment. | https://www.unitedrentals.com/marketplace/equipment/trench-safety-shoring |
| R24-06 | Steel road plate | ADDED | Construction & Industrial Equipment → Trench & Shoring → Steel Road Plates | Site equipment; load/site conditions remain listing details. | https://www.unitedrentals.com/marketplace/equipment/trench-safety-shoring |
| R24-07 | Composite trench cover | ADDED | Construction & Industrial Equipment → Trench & Shoring → Composite Trench Covers | Site equipment; load/site conditions remain listing details. | https://www.unitedrentals.com/marketplace/equipment/trench-safety-shoring |
| R24-08 | Temporary guardrail | ADDED | Construction & Industrial Equipment → Trench & Shoring → Temporary Guardrails | Safety-critical equipment; installation/use conditions remain listing requirements. | https://www.unitedrentals.com/marketplace/equipment/trench-safety-shoring |
| R24-09 | Trench bridge | ADDED | Construction & Industrial Equipment → Trench & Shoring → Trench Bridges | Site equipment; load/site conditions remain listing details. | https://www.unitedrentals.com/marketplace/equipment/trench-safety-shoring |
| R24-10 | Pipe plug | ALIAS_MAPPED | Tools & Equipment → Plumbing & Pipe Tools → Pipe Plugs | This is a plumbing-tool path already introduced for the overlapping reference. | https://www.unitedrentals.com/marketplace/equipment/trench-safety-shoring |
| R24-11 | Manhole vacuum tester | ADDED | Construction & Industrial Equipment → Trench & Shoring → Manhole Vacuum Testers | Safety-critical equipment; operating procedure remains listing responsibility. | https://www.unitedrentals.com/marketplace/equipment/trench-safety-shoring |
| R24-12 | Davit or tripod retrieval system | ADDED | Construction & Industrial Equipment → Trench & Shoring → Davit & Tripod Retrieval Systems | Safety-critical equipment; operating procedure remains listing responsibility. | https://www.unitedrentals.com/marketplace/equipment/trench-safety-shoring |

## Status total — must equal 179

| Status | Count |
|---|---:|
| ADDED | 141 |
| ALIAS_MAPPED | 30 |
| KIT_COMPONENT_MAPPED | 4 |
| RENTAL_MODE_MAPPED | 1 |
| REVIEW_REQUIRED | 3 |
| **Total** | **179** |

The row count and each R-family count were verified locally against the supplied
R01–R24 cardinalities: **179 unique references**.
