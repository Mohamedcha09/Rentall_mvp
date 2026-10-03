# R25–R47 rental-research mapping proposal

**Purpose:** a read-only, implementation-planning input for the 333-entry
coverage manifest.  This document compares the supplied R25–R47 source
entries (154 entries) with the current `app/rental_catalog.py` tree.  It does
not claim that any proposed row has been added yet.

Status meanings: **EXISTING** = exact current leaf; **ALIAS_MAPPED** = map a
source term/search synonym to an existing leaf without duplicating it;
**ADDED** = proposed missing canonical L2/L3 row; **KIT_COMPONENT_MAPPED** =
a supplied component belongs to a rentable kit rather than an independent
listing; **RENTAL_MODE_MAPPED** = the supplied entry is a way of offering an
asset/space, not a separate asset taxonomy node; **REVIEW_REQUIRED** = keep
out of the active self-service catalog pending a specific compliance workflow.
`[new]` identifies a proposed row.  All proposed L3 branches should retain
the existing parent-scoped `Other` behavior where the implementation adds L3
choices.

## R25 — Portable facilities

Current coverage: `Temporary Infrastructure & Site Services` already has
`Sanitation` and `Mobile Offices & Structures`; `Warehousing & Logistics`
already has storage-container leaves.

Sources: <https://www.unitedrentals.com/marketplace/equipment>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R25-01 | Portable toilet | EXISTING | `Temporary Infrastructure & Site Services → Sanitation → Portable Toilets` | Deliver/install terms remain listing terms. |
| R25-02 | Mobile shower | EXISTING | `Temporary Infrastructure & Site Services → Sanitation → Mobile Showers` | Deliver/install terms remain listing terms. |
| R25-03 | Handwashing station | ALIAS_MAPPED | `Temporary Infrastructure & Site Services → Sanitation → Handwash Stations` | Singular source label maps to current plural leaf. |
| R25-04 | Mobile office | EXISTING | `Temporary Infrastructure & Site Services → Mobile Offices & Structures → Mobile Offices` | Asset rental. |
| R25-05 | Storage container | ALIAS_MAPPED | `Warehousing & Logistics → Storage & Containers → Mobile Storage Containers` | Generic source term; do not duplicate `Shipping Containers`. |
| R25-06 | Refrigerated container | ADDED | `Warehousing & Logistics → Storage & Containers → Refrigerated Containers [new]` | Distinct temperature-controlled asset. |
| R25-07 | Temporary industrial tent | ALIAS_MAPPED | `Temporary Infrastructure & Site Services → Mobile Offices & Structures → Temporary Structures` | Industrial tent is a temporary-structure synonym; size/install stays a listing attribute. |

## R26 — Moving tools

Current coverage: `Warehousing & Logistics → Pallet & Manual Handling` has
`Dollies`, `Hand Trucks`, and `Utility Carts`.

Sources: <https://www.wbrental.com/moving-equipment.html>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R26-01 | Air-cushion appliance lifter | ADDED | `Warehousing & Logistics → Pallet & Manual Handling → Air-Cushion Appliance Lifters [new]` | Meaningfully distinct lifting method. |
| R26-02 | Appliance dolly | ALIAS_MAPPED | `Warehousing & Logistics → Pallet & Manual Handling → Dollies` | Appliance use is a search alias, not a duplicate node. |
| R26-03 | Powered stair-climbing dolly | ADDED | `Warehousing & Logistics → Pallet & Manual Handling → Powered Stair-Climbing Dollies [new]` | Distinct powered moving equipment. |
| R26-04 | Utility hand truck | ALIAS_MAPPED | `Warehousing & Logistics → Pallet & Manual Handling → Hand Trucks` | “Utility” is a use qualifier. |
| R26-05 | Heavy-duty inflatable-equipment dolly | ALIAS_MAPPED | `Warehousing & Logistics → Pallet & Manual Handling → Dollies` | Heavy-duty/use configuration is not a separate equipment identity. |
| R26-06 | Tree dolly | ADDED | `Warehousing & Logistics → Pallet & Manual Handling → Tree Dollies [new]` | Specialized nursery/moving asset. |
| R26-07 | Four-wheel furniture dolly | ALIAS_MAPPED | `Warehousing & Logistics → Pallet & Manual Handling → Dollies` | Wheel count/furniture use is a description/search alias. |
| R26-08 | Three-wheel furniture dolly set | ALIAS_MAPPED | `Warehousing & Logistics → Pallet & Manual Handling → Dollies` | Set/wheel configuration remains listing inventory detail. |

## R27 — Surveying instruments

Current coverage: `Tools & Equipment → Surveying & Inspection` has generic
`Laser Levels` and `Total Stations`, but not the listed specialist leaves.

Sources: <https://g2survey.com/hire/>, <https://www.sccssurvey.co.uk/>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R27-01 | 3D laser scanner | ADDED | `Tools & Equipment → Surveying & Inspection → 3D Laser Scanners [new]` | Standalone instrument. |
| R27-02 | Robotic total station | ADDED | `Tools & Equipment → Surveying & Inspection → Robotic Total Stations [new]` | Distinct automation class. |
| R27-03 | Manual total station | ALIAS_MAPPED | `Tools & Equipment → Surveying & Inspection → Total Stations` | Current generic leaf represents ordinary/manual units. |
| R27-04 | GNSS survey receiver | ADDED | `Tools & Equipment → Surveying & Inspection → GNSS Survey Receivers [new]` | Standalone instrument. |
| R27-05 | Digital level | ADDED | `Tools & Equipment → Surveying & Inspection → Digital Levels [new]` | Distinct instrument. |
| R27-06 | Automatic optical level | ADDED | `Tools & Equipment → Surveying & Inspection → Automatic Optical Levels [new]` | Distinct optical instrument. |
| R27-07 | Rotating laser level | ALIAS_MAPPED | `Tools & Equipment → Surveying & Inspection → Laser Levels` | Rotating form is a search alias under the present generic leaf. |
| R27-08 | Pipe laser | ADDED | `Tools & Equipment → Surveying & Inspection → Pipe Lasers [new]` | Specialized survey/installation tool. |
| R27-09 | Underground utility detector | ADDED | `Tools & Equipment → Surveying & Inspection → Underground Utility Detectors [new]` | Distinct detection instrument. |

## R28 — Electrical/electronic test instruments

Current coverage: `Tools & Equipment → Electrical & Testing Tools` is only a
two-level broad branch.  The volume and specialist nature of R28 plus R29
justify one new L1: `Test & Measurement [new]`, with an `Electrical Test
Instruments [new]` L2.  This leaves the current hand-tool branch untouched.

Sources: <https://www.transcat.ca/rental-equipment/electrical-instrument>, <https://jmtest.ca/pages/rentals>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R28-01 | Ground resistance tester | ADDED | `Test & Measurement [new] → Electrical Test Instruments [new] → Ground Resistance Testers [new]` | Specialist reusable instrument. |
| R28-02 | Low-resistance ohmmeter | ADDED | `Test & Measurement [new] → Electrical Test Instruments [new] → Low-Resistance Ohmmeters [new]` | Specialist reusable instrument. |
| R28-03 | Insulation resistance tester | ADDED | `Test & Measurement [new] → Electrical Test Instruments [new] → Insulation Resistance Testers [new]` | Specialist reusable instrument. |
| R28-04 | Phase meter | ADDED | `Test & Measurement [new] → Electrical Test Instruments [new] → Phase Meters [new]` | Specialist reusable instrument. |
| R28-05 | Cable locator | ADDED | `Test & Measurement [new] → Electrical Test Instruments [new] → Cable Locators [new]` | Specialist reusable instrument. |
| R28-06 | Clamp meter | ADDED | `Test & Measurement [new] → Electrical Test Instruments [new] → Clamp Meters [new]` | Specialist reusable instrument. |
| R28-07 | High-voltage meter | ADDED | `Test & Measurement [new] → Electrical Test Instruments [new] → High-Voltage Meters [new]` | Specialist reusable instrument. |
| R28-08 | Hipot tester | ADDED | `Test & Measurement [new] → Electrical Test Instruments [new] → Hipot Testers [new]` | Specialist reusable instrument. |
| R28-09 | Electronic load | ADDED | `Test & Measurement [new] → Electrical Test Instruments [new] → Electronic Loads [new]` | Do not confuse with temporary-power load banks. |
| R28-10 | Network cable tester | ADDED | `Test & Measurement [new] → Electrical Test Instruments [new] → Network Cable Testers [new]` | Reusable network test equipment. |
| R28-11 | Optical test equipment | ADDED | `Test & Measurement [new] → Electrical Test Instruments [new] → Optical Test Equipment [new]` | Broad source family; do not invent optical subtypes. |
| R28-12 | Power analyzer | ADDED | `Test & Measurement [new] → Electrical Test Instruments [new] → Power Analyzers [new]` | Specialist reusable instrument. |
| R28-13 | RF amplifier | ADDED | `Test & Measurement [new] → Electrical Test Instruments [new] → RF Amplifiers [new]` | Test/communications equipment, not consumer audio amplification. |
| R28-14 | Solar PV tester | ADDED | `Test & Measurement [new] → Electrical Test Instruments [new] → Solar PV Testers [new]` | Specialist reusable instrument. |

## R29 — Environmental monitoring

Current coverage: no environmental-monitoring branch.  Use the same proposed
`Test & Measurement [new]` L1 and an `Environmental Monitoring [new]` L2;
do not put monitoring instruments under temporary air-treatment equipment.

Sources: <https://www.enviroequipment.com/>, <https://usenvironmental.com/>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R29-01 | Water quality meter | ADDED | `Test & Measurement [new] → Environmental Monitoring [new] → Water Quality Meters [new]` | Reusable meter. |
| R29-02 | Water sampling equipment | ADDED | `Test & Measurement [new] → Environmental Monitoring [new] → Water Sampling Equipment [new]` | Reusable sampler hardware only; consumable sample media excluded. |
| R29-03 | Water-level meter | ADDED | `Test & Measurement [new] → Environmental Monitoring [new] → Water-Level Meters [new]` | Reusable meter. |
| R29-04 | Pressure transducer | ADDED | `Test & Measurement [new] → Environmental Monitoring [new] → Pressure Transducers [new]` | Reusable instrument. |
| R29-05 | Flow probe | ADDED | `Test & Measurement [new] → Environmental Monitoring [new] → Flow Probes [new]` | Reusable probe. |
| R29-06 | Gas detector | ADDED | `Test & Measurement [new] → Environmental Monitoring [new] → Gas Detectors [new]` | Calibration/safety terms stay listing requirements. |
| R29-07 | PID detector | ADDED | `Test & Measurement [new] → Environmental Monitoring [new] → PID Detectors [new]` | Distinct gas-detection method. |
| R29-08 | Noise or sound meter | ADDED | `Test & Measurement [new] → Environmental Monitoring [new] → Sound Meters [new]` | Broad source label maps to one clear meter family. |
| R29-09 | Indoor air monitoring equipment | ADDED | `Test & Measurement [new] → Environmental Monitoring [new] → Indoor Air Monitoring Equipment [new]` | Monitoring, not air-scrubbing. |

## R30 — Professional laboratory equipment

Current coverage: `Books & Learning → Lab & Science Kits` is educational and
does not safely represent professional/clinical equipment.  The current audit
explicitly excludes regulated medical-device branches from active self-service
listing.  Proposed future path only: `Laboratory Equipment [gated] → Lab
Equipment & Instrument Access [gated]`.

Sources: <https://www.aurevia.com/services/clinical-research/pharma/medical-and-laboratory-equipment-rental/>, <https://www.waters.com/nextgen/ca/en/services/payment-solutions/rental.html>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R30-01 | Centrifuge | REVIEW_REQUIRED | `Laboratory Equipment [gated] → Lab Equipment & Instrument Access [gated] → Centrifuges` | Professional/device suitability and cleaning workflow required. |
| R30-02 | Refrigerated centrifuge | REVIEW_REQUIRED | `Laboratory Equipment [gated] → Lab Equipment & Instrument Access [gated] → Refrigerated Centrifuges` | Same gating; refrigeration is not merely a display label. |
| R30-03 | Laboratory refrigerator | REVIEW_REQUIRED | `Laboratory Equipment [gated] → Lab Equipment & Instrument Access [gated] → Laboratory Refrigerators` | Temperature-chain/cleaning requirements. |
| R30-04 | Low-temperature laboratory freezer | REVIEW_REQUIRED | `Laboratory Equipment [gated] → Lab Equipment & Instrument Access [gated] → Low-Temperature Laboratory Freezers` | Temperature-chain/compliance requirements. |
| R30-05 | Temperature data logger | REVIEW_REQUIRED | `Laboratory Equipment [gated] → Lab Equipment & Instrument Access [gated] → Temperature Data Loggers` | Gated with lab workflow, not ordinary consumer electronics. |
| R30-06 | Analytical instrument rental | REVIEW_REQUIRED | `Laboratory Equipment [gated] → Lab Equipment & Instrument Access [gated] → Analytical Instruments` | Often long-term installed/trained rental program; not a generic daily listing. |

## R31 — Lawn and garden equipment

Current coverage: `Agriculture & Landscaping → Lawn & Garden` already has
`Mowers`, `Aerators`, and `Trimmers`; `Seeders` is under `Tractors &
Implements`.

Sources: <https://www.wbrental.com/lawn--garden-equipment.html>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R31-01 | Lawn aerator | ALIAS_MAPPED | `Agriculture & Landscaping → Lawn & Garden → Aerators` | Singular source label maps to existing leaf. |
| R31-02 | Brush mower | ALIAS_MAPPED | `Agriculture & Landscaping → Lawn & Garden → Mowers` | Mower use/type is a search alias, avoiding a near-duplicate. |
| R31-03 | Slit seeder | ALIAS_MAPPED | `Agriculture & Landscaping → Tractors & Implements → Seeders` | Current generic seeder leaf covers it. |
| R31-04 | Lawn dethatcher | ADDED | `Agriculture & Landscaping → Lawn & Garden → Lawn Dethatchers [new]` | Distinct lawn-maintenance equipment. |
| R31-05 | Broadcast seed spreader | ADDED | `Agriculture & Landscaping → Lawn & Garden → Broadcast Seed Spreaders [new]` | Spreaders and seeders are different equipment. |
| R31-06 | Sod cutter | ADDED | `Agriculture & Landscaping → Lawn & Garden → Sod Cutters [new]` | Distinct turf-removal equipment. |

## R32 — Agricultural equipment and attachments

Current coverage: `Agriculture & Landscaping` has `Tractors & Implements`,
`Lawn & Garden`, and `Livestock & Farm Handling`; it lacks the supplied
specialist leaves.

Sources: <https://www.coppard.co.uk/crowborough/plant-and-machinery-hire/agricultural-equipment-hire/>, <https://grazihire.com.au/>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R32-01 | Tractor | ADDED | `Agriculture & Landscaping → Tractors & Implements → Tractors [new]` | Broad source term must not be silently narrowed to `Compact Tractors`. |
| R32-02 | Utility terrain vehicle | ADDED | `Agriculture & Landscaping → Tractors & Implements → Utility Terrain Vehicles [new]` | Farm/off-road purpose is clearer here than passenger-vehicle branches. |
| R32-03 | Cultivation equipment | ADDED | `Agriculture & Landscaping → Tractors & Implements → Cultivation Equipment [new]` | Keep source-general wording; do not invent implement subtype. |
| R32-04 | Post-hole borer | ADDED | `Agriculture & Landscaping → Tractors & Implements → Post-Hole Borers [new]` | Distinct attachment/tool family. |
| R32-05 | Hedge cutter | ADDED | `Agriculture & Landscaping → Lawn & Garden → Hedge Cutters [new]` | More specific than current general trimmers. |
| R32-06 | Agricultural trailer | ADDED | `Agriculture & Landscaping → Tractors & Implements → Agricultural Trailers [new]` | Agricultural-use trailer stays distinguishable from road trailers. |
| R32-07 | Fencing equipment | ADDED | `Agriculture & Landscaping → Livestock & Farm Handling → Fencing Equipment [new]` | Farm-fencing equipment is not temporary event/site fencing. |

## R33 — Honey and small-harvest processing

Current coverage: no small-harvest-processing branch.  Add a focused L2
under `Agriculture & Landscaping`; do not offer documented kit components as
standalone rentals without separate evidence.

Sources: <https://www.foxhoundbeecompany.com/en-ca/products/rental-honey-extractor-kit-3-frame-manual>, <https://www.dulra.org/courses/apple-press-hiredemo>, <https://www.slorchards.com/press-hire>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R33-01 | Honey extractor kit | ADDED | `Agriculture & Landscaping → Small-Harvest Processing [new] → Honey Extractor Kits [new]` | Rentable kit. |
| R33-02 | Uncapping fork | KIT_COMPONENT_MAPPED | `Agriculture & Landscaping → Small-Harvest Processing → Honey Extractor Kits` | Documented kit component; not independently evidenced. |
| R33-03 | Honey strainer | KIT_COMPONENT_MAPPED | `Agriculture & Landscaping → Small-Harvest Processing → Honey Extractor Kits` | Documented kit component; not independently evidenced. |
| R33-04 | Uncapping tank | KIT_COMPONENT_MAPPED | `Agriculture & Landscaping → Small-Harvest Processing → Honey Extractor Kits` | Documented kit component; not independently evidenced. |
| R33-05 | Uncapping knife | KIT_COMPONENT_MAPPED | `Agriculture & Landscaping → Small-Harvest Processing → Honey Extractor Kits` | Documented kit component; not independently evidenced. |
| R33-06 | Apple crusher | ADDED | `Agriculture & Landscaping → Small-Harvest Processing → Apple Crushers [new]` | Rentable processing equipment. |
| R33-07 | Apple press | ADDED | `Agriculture & Landscaping → Small-Harvest Processing → Apple Presses [new]` | Rentable processing equipment. |
| R33-08 | Orchard tripod ladder | ADDED | `Agriculture & Landscaping → Small-Harvest Processing → Orchard Tripod Ladders [new]` | Purpose-specific reusable access equipment. |

## R34 — POS, registration, and inventory hardware

Current coverage: `Retail & Vending Equipment → POS & Checkout` already has
`Barcode Scanners`; `Warehousing & Logistics → Packaging & Labeling` has
`Label Printers`.

Sources: <https://hardware.shopify.com/pages/hardware-rental-program>, <https://eventinabox.cvent.com/s/product/event-in-a-box-handheld-barcode-scanner-rental/01t2G0000065TNoQAM>, <https://www.midcomservicegroup.com/barcode-scanner-rental>, <https://choose2rent.com/rentals/badge-printers/direct-thermal/>, <https://allrent.eu/barcode-scanner-rental/>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R34-01 | POS hardware kit | ADDED | `Retail & Vending Equipment → POS & Checkout → POS Hardware Kits [new]` | Hardware only; never a merchant identity/payment account. |
| R34-02 | Handheld barcode scanner | ALIAS_MAPPED | `Retail & Vending Equipment → POS & Checkout → Barcode Scanners` | Handheld form is a current-leaf synonym. |
| R34-03 | Inventory scanning terminal | ADDED | `Retail & Vending Equipment → POS & Checkout → Inventory Scanning Terminals [new]` | Distinct portable terminal class. |
| R34-04 | Thermal badge printer | ADDED | `Retail & Vending Equipment → POS & Checkout → Thermal Badge Printers [new]` | Paper/badges remain consumables. |
| R34-05 | Thermal label printer | ALIAS_MAPPED | `Warehousing & Logistics → Packaging & Labeling → Label Printers` | Thermal technology is a variant; labels are consumables. |

## R35 — Retail display equipment

Current coverage: `Retail & Vending Equipment → Display & Merchandising`
already has `Mannequins` and `Display Cases`.

Sources: <https://mannakin.com/p/faceless-vanessa/>, <https://www.expohire.com/product/ex-man-kid/child-mannequin>, <https://www.showfront.com.au/cabinet-hire>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R35-01 | Adult display mannequin | ALIAS_MAPPED | `Retail & Vending Equipment → Display & Merchandising → Mannequins` | Age/style is a listing attribute. |
| R35-02 | Child display mannequin | ALIAS_MAPPED | `Retail & Vending Equipment → Display & Merchandising → Mannequins` | Age/style is a listing attribute. |
| R35-03 | Glass display cabinet | ALIAS_MAPPED | `Retail & Vending Equipment → Display & Merchandising → Display Cases` | Glass is a construction/material attribute. |

## R36 — Film camera and production audio

Current coverage: `Electronics → Cameras & Video` has `Cinema Cameras` and
generic `Lenses`; `Events & Production Equipment → Audio Equipment` has
generic `Microphones` and `Mixers`.

Sources: <https://prggear.com/product-category/camera-rental/>, <https://everythingfilmequipment.com/>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R36-01 | Cinema camera | EXISTING | `Electronics → Cameras & Video → Cinema Cameras` | Exact current leaf. |
| R36-02 | Broadcast camera | ADDED | `Electronics → Cameras & Video → Broadcast Cameras [new]` | Distinct production camera use. |
| R36-03 | Cinema prime lens | ADDED | `Electronics → Cameras & Video → Cinema Prime Lenses [new]` | Meaningful optical type. |
| R36-04 | Cinema zoom lens | ADDED | `Electronics → Cameras & Video → Cinema Zoom Lenses [new]` | Meaningful optical type. |
| R36-05 | Anamorphic lens | ADDED | `Electronics → Cameras & Video → Anamorphic Lenses [new]` | Meaningful optical type. |
| R36-06 | Director viewfinder | ADDED | `Electronics → Cameras & Video → Director Viewfinders [new]` | Distinct previsualization equipment. |
| R36-07 | Lavalier microphone | ADDED | `Events & Production Equipment → Audio Equipment → Lavalier Microphones [new]` | Distinct microphone form factor. |
| R36-08 | Shotgun microphone | ADDED | `Events & Production Equipment → Audio Equipment → Shotgun Microphones [new]` | Distinct microphone form factor. |
| R36-09 | Boom pole | ADDED | `Events & Production Equipment → Audio Equipment → Boom Poles [new]` | Reusable audio-support hardware. |
| R36-10 | Audio mixer | ALIAS_MAPPED | `Events & Production Equipment → Audio Equipment → Mixers` | Singular source label maps to current leaf. |

## R37 — Displays and live production

Current coverage: `Events & Production Equipment` already has `LED Walls`,
`Stage Platforms`, video/audio/lighting branches; `Electronics` owns generic
projectors, projection screens, and monitors.

Sources: <https://prggear.com/>, <https://www.torontoaudiovisualrentals.ca/conference-equipment-rental-toronto.php>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R37-01 | LED video wall | EXISTING | `Events & Production Equipment → Video & Displays → LED Walls` | Exact current leaf. |
| R37-02 | Video projector | ALIAS_MAPPED | `Electronics → Office Tech → Projectors` | Event use is a listing context, not duplicate equipment. |
| R37-03 | Projection screen | EXISTING | `Electronics → Office Tech → Projection Screens` | Exact current leaf. |
| R37-04 | Presentation monitor | ALIAS_MAPPED | `Electronics → Computers & Tablets → Monitors` | Presentation use is a listing context. |
| R37-05 | Media server | ADDED | `Events & Production Equipment → Video & Displays → Media Servers [new]` | Live-production hardware. |
| R37-06 | Video production equipment | ADDED | `Events & Production Equipment → Video & Displays → Video Production Systems [new]` | May be standalone or a kit; crew is not encoded as a type. |
| R37-07 | Stage lighting | ALIAS_MAPPED | `Events & Production Equipment → Lighting Equipment` | Broad system family already exists; fixture/model stays a listing detail. |
| R37-08 | Rigging equipment | ADDED | `Events & Production Equipment → Rigging & Truss [new] → Rigging Equipment [new]` | Separate safety-critical production family. |
| R37-09 | Conference audio system | ADDED | `Events & Production Equipment → Audio Equipment → Conference Audio Systems [new]` | System-level equipment family. |
| R37-10 | Stage platform | EXISTING | `Events & Production Equipment → Staging & Flooring → Stage Platforms` | Exact current leaf. |
| R37-11 | Pipe-and-drape system | ADDED | `Events & Production Equipment → Event Draping & Backdrops [new] → Pipe-and-Drape Systems [new]` | Event-environment hardware, not a consumable backdrop. |

## R38 — Interpretation and tour audio

Current coverage: no dedicated interpretation/tour-audio branch.  Add one
focused L2 below `Events & Production Equipment`.

Sources: <https://www.brombergtranslations.com/simultaneous-interpreting-conference-equipment-rental-solutions/>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R38-01 | Soundproof interpretation booth | ADDED | `Events & Production Equipment → Interpretation & Tour Audio [new] → Soundproof Interpretation Booths [new]` | Equipment only; interpreter staffing is separate. |
| R38-02 | Wireless interpretation receiver | ADDED | `Events & Production Equipment → Interpretation & Tour Audio [new] → Wireless Interpretation Receivers [new]` | Reusable receiver hardware. |
| R38-03 | Interpretation headset | ADDED | `Events & Production Equipment → Interpretation & Tour Audio [new] → Interpretation Headsets [new]` | Hygiene/earpiece terms stay listing requirements. |
| R38-04 | Portable tour audio system | ADDED | `Events & Production Equipment → Interpretation & Tour Audio [new] → Portable Tour Audio Systems [new]` | System-level equipment. |

## R39 — Musical instruments and recording

Current coverage: `Music & Performance Equipment` already has `Guitars`,
`Keyboards`, `Drum Kits`, amplification leaves, and event audio has generic
`Microphones`.

Sources: <https://www.long-mcquade.com/rentals/>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R39-01 | Guitar | EXISTING | `Music & Performance Equipment → Musical Instruments → Guitars` | Exact current leaf. |
| R39-02 | Bass guitar | ADDED | `Music & Performance Equipment → Musical Instruments → Bass Guitars [new]` | Distinct instrument, not a guitar finish/model. |
| R39-03 | Drum kit | EXISTING | `Music & Performance Equipment → Musical Instruments → Drum Kits` | Exact current leaf. |
| R39-04 | Keyboard or synthesizer | ALIAS_MAPPED | `Music & Performance Equipment → Musical Instruments → Keyboards` | Current generic keyboard leaf covers source’s alternative wording. |
| R39-05 | Orchestral instrument | ADDED | `Music & Performance Equipment → Musical Instruments → Orchestral Instruments [new]` | Keep source-general rather than inventing wind/brass subtypes. |
| R39-06 | Instrument amplifier | ADDED | `Music & Performance Equipment → Amplification & Backline → Instrument Amplifiers [new]` | Generic source term should not be forced to guitar/bass/keyboard. |
| R39-07 | Microphone | EXISTING | `Events & Production Equipment → Audio Equipment → Microphones` | Existing cross-category audio leaf; do not duplicate. |
| R39-08 | Recording equipment | ADDED | `Music & Performance Equipment → Rehearsal & Performance Gear → Recording Equipment [new]` | Reusable recording family; not a crew/service claim. |

## R40 — Art and plant rental

Current coverage: `Furniture → Rugs & Decor` is the closest established
decorative-asset branch.  Two additions are preferable to a new L1 with only
two leaves.

Sources: <https://artbank.ca/art-rental>, <https://oaggao.ca/shop-dine/galerie-annexe/purchase-or-rent-art/>, <https://www.serrescleroux.com/en/category/online-store/2058-tropical-plant-rental.html>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R40-01 | Artwork rental | ADDED | `Furniture → Rugs & Decor → Artwork Rentals [new]` | Physical asset rental only; no copyright/license implication. |
| R40-02 | Tropical plant rental | ADDED | `Furniture → Rugs & Decor → Tropical Plant Rentals [new]` | Delivery/care terms stay listing terms. |

## R41 — Workspaces and commercial experiences

Current coverage: `Spaces & Studios` has event venues and maker spaces, but
not a pop-up retail leaf or on-site machine-workstation leaves.  The latter
are intentionally space/time modes, distinct from taking a `Sewing Machine`
or `Heat Press` home.

Sources: <https://www.thestorefront.com/>, <https://espacefabrik.com/en/products/location-de-machine>, <https://www.herdcreations.com/products/heat-press-space-rental>, <https://www.medacespace.com/products/equipment/>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R41-01 | Pop-up retail space | ADDED | `Spaces & Studios → Retail & Pop-up Spaces [new] → Pop-up Retail Spaces [new]` | Space booking, not retail fixture equipment. |
| R41-02 | Event space | ADDED | `Spaces & Studios → Event Venues → Event Spaces [new]` | Broad source term cannot be assumed to be a hall/room/outdoor venue. |
| R41-03 | Sewing workstation | RENTAL_MODE_MAPPED | `Spaces & Studios → Workshops & Maker Spaces → Sewing Workstations [new]` | On-site workstation/time; do not duplicate take-away sewing machines. |
| R41-04 | Heat-press workstation | RENTAL_MODE_MAPPED | `Spaces & Studios → Workshops & Maker Spaces → Heat-Press Workstations [new]` | On-site workstation/time; distinct from take-away heat presses. |
| R41-05 | Laboratory equipment time slot | REVIEW_REQUIRED | `Laboratory Equipment [gated] → Lab Equipment & Instrument Access [gated] → Laboratory Equipment Time Slots` | Requires the same lab/compliance workflow as R30. |

## R42 — Baby and family equipment

Current coverage: `Baby & Kids` has suitable L2 parents but no L3 leaves.
All R42 entries are ordinary reusable equipment/kit categories; age, fit,
sanitation, and condition remain listing requirements.

Sources: <https://www.babyquip.com/>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R42-01 | Crib | ADDED | `Baby & Kids → Nursery & Sleep → Cribs [new]` | Reusable equipment. |
| R42-02 | Car seat | ADDED | `Baby & Kids → Travel & Safety → Car Seats [new]` | Fit/expiry/inspection not encoded in taxonomy. |
| R42-03 | Stroller | ADDED | `Baby & Kids → Travel & Safety → Strollers [new]` | Reusable equipment. |
| R42-04 | Child wagon | ADDED | `Baby & Kids → Travel & Safety → Child Wagons [new]` | Reusable equipment. |
| R42-05 | High chair | ADDED | `Baby & Kids → Nursery & Sleep → High Chairs [new]` | Reusable equipment. |
| R42-06 | Baby bathing equipment | ADDED | `Baby & Kids → Nursery & Sleep → Baby Bathing Equipment [new]` | Broad source term; do not invent bath subtype. |
| R42-07 | Bouncer | ADDED | `Baby & Kids → Nursery & Sleep → Bouncers [new]` | Reusable equipment. |
| R42-08 | Baby swing | ADDED | `Baby & Kids → Nursery & Sleep → Baby Swings [new]` | Reusable equipment. |
| R42-09 | Toys books and games kit | ADDED | `Baby & Kids → Toys & Play → Toy, Book & Game Kits [new]` | Kit is rentable; individual consumables excluded. |

## R43 — Accessibility and mobility

Current coverage: none.  The existing audit explicitly keeps medical and
mobility-device leasing out of the active self-service catalog pending
jurisdiction-specific provider/compliance review.  Future proposed path only:
`Accessibility & Mobility [gated] → Mobility Equipment [gated]`.

Sources: <https://scootaround.com/en/mobility-scooter-rentals>, <https://www.akamaimobility.com/product-category/mobility-equipment-rentals/>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R43-01 | Transportable mobility scooter | REVIEW_REQUIRED | `Accessibility & Mobility [gated] → Mobility Equipment [gated] → Transportable Mobility Scooters` | Medical/safety suitability and provider review required. |
| R43-02 | Standard mobility scooter | REVIEW_REQUIRED | `Accessibility & Mobility [gated] → Mobility Equipment [gated] → Standard Mobility Scooters` | Same gating. |
| R43-03 | Heavy-duty mobility scooter | REVIEW_REQUIRED | `Accessibility & Mobility [gated] → Mobility Equipment [gated] → Heavy-Duty Mobility Scooters` | Same gating; capacity is not otherwise a taxonomy axis. |
| R43-04 | Rollator | REVIEW_REQUIRED | `Accessibility & Mobility [gated] → Mobility Equipment [gated] → Rollators` | Same gating. |
| R43-05 | Bed rail | REVIEW_REQUIRED | `Accessibility & Mobility [gated] → Mobility Equipment [gated] → Bed Rails` | Same gating. |
| R43-06 | Bathtub rail | REVIEW_REQUIRED | `Accessibility & Mobility [gated] → Mobility Equipment [gated] → Bathtub Rails` | Same gating. |
| R43-07 | Crutch holder | REVIEW_REQUIRED | `Accessibility & Mobility [gated] → Mobility Equipment [gated] → Crutch Holders` | Same gating; accessory remains tied to mobility workflow. |

## R44 — Camping and paddling

Current coverage: `Sports & Outdoors → Camping & Outdoors` already has
`Tents` and `Sleeping Bags`; `Water Sports` has `Kayaks`, `Canoes`, and
`Paddleboards`.

Sources: <https://thamesvalleyoutfitters.ca/>, <https://livelifeintents.com/camping-gear-rental>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R44-01 | Camping tent | ALIAS_MAPPED | `Sports & Outdoors → Camping & Outdoors → Tents` | Source wording maps to current leaf. |
| R44-02 | Sleeping equipment kit | ADDED | `Sports & Outdoors → Camping & Outdoors → Sleeping Equipment Kits [new]` | Rentable kit, not an assertion that each component rents alone. |
| R44-03 | Camping equipment kit | ADDED | `Sports & Outdoors → Camping & Outdoors → Camping Equipment Kits [new]` | Rentable kit. |
| R44-04 | Packraft | ADDED | `Sports & Outdoors → Water Sports → Packrafts [new]` | Distinct compact watercraft. |
| R44-05 | Canoe | EXISTING | `Sports & Outdoors → Water Sports → Canoes` | Exact current leaf. |
| R44-06 | Kayak | EXISTING | `Sports & Outdoors → Water Sports → Kayaks` | Exact current leaf. |
| R44-07 | Stand-up paddleboard | ALIAS_MAPPED | `Sports & Outdoors → Water Sports → Paddleboards` | Source wording maps to current leaf. |

## R45 — Vehicle travel accessory

Current coverage: no accessory L2 below `Vehicles`; a roof cargo box is not a
trailer/RV and should not be forced into those branches.

Sources: <https://www.audiwinnipeg.com/en/audi-roof-box-rental-program/>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R45-01 | Roof cargo box | ADDED | `Vehicles → Vehicle Travel Accessories [new] → Roof Cargo Boxes [new]` | Vehicle compatibility is a listing requirement, not per-model taxonomy. |

## R46 — Yachts and watercraft

Current coverage: `Marine & Watercraft → Boats` has generic `Sailboats` but
not the supplied yacht types.  Crew is a booking/service term rather than a
watercraft type.

Sources: <https://www.moorings.com/yachts>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R46-01 | Sailing catamaran | ADDED | `Marine & Watercraft → Boats → Sailing Catamarans [new]` | Distinct hull/configuration class. |
| R46-02 | Monohull sailboat | ADDED | `Marine & Watercraft → Boats → Monohull Sailboats [new]` | Add while retaining existing generic/legacy `Sailboats`. |
| R46-03 | Power yacht | ADDED | `Marine & Watercraft → Boats → Power Yachts [new]` | Distinct powered yacht class. |
| R46-04 | Crewed yacht charter | RENTAL_MODE_MAPPED | `Marine & Watercraft → Boats → applicable boat type` | Crew/charter must be an explicit future listing mode/verification field, not L3; do not activate it as a self-service type. |

## R47 — Aviation and helicopter charter

Current coverage: none.  The active rental catalog deliberately excludes
aviation and crewed charter.  All entries are professional charter services,
not self-operated asset rentals, so a future gated path only is appropriate:
`Aviation [gated] → Professional Air Charter [gated]`.

Sources: <https://www.aircharterservice.com/aircraft-guide/>, <https://www.aircharterservice.ca/private-charter/helicopter>, <https://lrhelicopters.com/helicopter-charter/>

| Reference | Source label | Proposed status | Canonical path / reason | Mode or component note |
| --- | --- | --- | --- | --- |
| R47-01 | Private aircraft charter | REVIEW_REQUIRED | `Aviation [gated] → Professional Air Charter [gated] → Private Aircraft Charter` | Licensed operator, insurance, custody/control, and passenger workflow needed. |
| R47-02 | Group passenger aircraft charter | REVIEW_REQUIRED | `Aviation [gated] → Professional Air Charter [gated] → Group Passenger Aircraft Charter` | Same charter/compliance gating. |
| R47-03 | Cargo aircraft charter | REVIEW_REQUIRED | `Aviation [gated] → Professional Air Charter [gated] → Cargo Aircraft Charter` | Same charter/compliance gating. |
| R47-04 | Helicopter charter | REVIEW_REQUIRED | `Aviation [gated] → Professional Air Charter [gated] → Helicopter Charter` | Same charter/compliance gating. |

## Audit totals for this slice

There are **154** references from R25-01 through R47-04.  All are represented
once above.  Status counts from this proposal: **ADDED 92**, **EXISTING 12**,
**ALIAS_MAPPED 25**, **KIT_COMPONENT_MAPPED 4**,
**RENTAL_MODE_MAPPED 3**, and **REVIEW_REQUIRED 18**.  The full 333-row
manifest must recompute totals after combining this slice with R01–R24 and
after any implementation choice changes a proposed mapping.
