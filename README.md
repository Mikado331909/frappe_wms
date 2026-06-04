# Frappe WMS

A full-featured **Warehouse Management System (WMS)** layer for ERPNext v16.  
Adds zone-based location tracking, directed putaway, QC, cross-docking, production staging, cycle counting and KPI reporting — all on top of ERPNext's standard stock ledger, without replacing it.

---

## Table of Contents

1. [Overview](#overview)
2. [Key Concepts](#key-concepts)
3. [Architecture](#architecture)
4. [DocTypes](#doctypes)
5. [Workflows](#workflows)
   - [Inbound – Standard Receipt](#inbound--standard-receipt)
   - [Inbound – QC Required](#inbound--qc-required)
   - [Inbound – Cross-dock](#inbound--cross-dock)
   - [Putaway – Move Stock](#putaway--move-stock)
   - [Outbound – Sales Order to Delivery](#outbound--sales-order-to-delivery)
   - [Manufacturing – Bulk Raw Material Picking](#manufacturing--bulk-raw-material-picking)
   - [Production Return – Inspection Zone](#production-return--inspection-zone)
   - [Cycle Counting](#cycle-counting)
6. [Picking Strategies](#picking-strategies)
7. [Customer Segregation](#customer-segregation)
8. [ERPNext v16 Compatibility](#erpnext-v16-compatibility)
9. [Configuration](#configuration)
10. [Installation](#installation)
11. [Reports](#reports)
12. [Design Decisions](#design-decisions)

---

## Overview

Frappe WMS tracks **where exactly** items sit within an ERPNext warehouse (zone → rack → bin) and **manages every physical movement** from receiving through delivery.

**What it does:**
- Organises warehouse into **zones** with dedicated customers and capacity limits
- Tracks batch stock per physical storage location with full customer segregation
- **Directed putaway** — system suggests the best location based on configurable rules
- Blocks mixing of different customers' stock on the same storage location
- **QC process** — items can be held for quality/quantity inspection before putaway
- **Cross-docking** — detected automatically via PO→SO links or flagged manually
- **Production bulk picking** — combine multiple Pick Lists into one Location Pick
- **Production return flow** — returned raw materials go to Inspection zone
- **Cycle counting** — zone-based stock counts with automatic BLS corrections
- Records every movement in an immutable audit trail with movement type and customer
- **4 KPI reports** — zone occupancy, customer stock, pick performance, inbound/outbound volume

**What it does NOT do:**
- Replace ERPNext's stock ledger — ERPNext remains the source of truth for quantities
- Manage serial numbers (batch tracking only)
- Handle non-batch-tracked items

**Supported ERPNext versions:** v16 (also backward-compatible with v15 batch field style)

---

## Key Concepts

### WMS Zone
A logical grouping of storage locations within one warehouse.  
Each zone has a **type** and optionally a **dedicated customer** — all locations in that zone then automatically belong to that customer.

| Zone Type | Purpose |
|---|---|
| `Receiving` | Goods land here on Purchase Receipt |
| `Active Storage` | Normal picking storage (racks, bins) |
| `QC Hold` | Items waiting for quality/quantity inspection |
| `Production Staging` | Raw materials bulk-picked, ready for cutting/production |
| `Outbound Staging` | Picked orders waiting for shipment |
| `Cross-dock Staging` | Goods passing straight through without storage |
| `Inspection` | Production returns awaiting evaluation |
| `Quarantine` | Rejected or damaged goods |

### Storage Location
A physical bin, shelf or rack inside a zone. Has a `pick_sequence` (aisle order), optional `max_qty` capacity, and an extended `location_type` that maps to the zone types above plus the legacy `Receiving` / `Storage` / `Picking Staging` values.

### Batch Location Stock (BLS)
The core inventory record: `item_code + batch_no + warehouse + storage_location → qty + customer + zone`.  
**Records are never deleted** — zero-qty records persist as history, mirroring ERPNext's own `Bin` doctype.

### Batch Location Movement
Immutable audit log of every qty change. Each entry carries `movement_type`:  
`Inbound | Putaway | Pick | Cross-dock | QC Release | Production | Production Return | Cycle Count | Manual`

### Location Pick
WMS pick task document generated from one or **multiple** ERPNext Pick Lists.  
Each line knows which Pick List it came from. On submit: stock moves from storage → staging.

### WMS Putaway Rule
Prioritised rules that map warehouse + customer + item group to a target zone.  
The putaway engine evaluates rules in priority order and suggests the best location (preferring consolidation with existing stock of the same customer).

---

## Architecture

```
ERPNext Events (hooks)
├── Purchase Receipt  on_submit / on_cancel
│       ├── Normal items   → RECV location
│       ├── QC flagged     → QC Hold location  +  WMS QC Check created
│       └── Cross-dock     → Cross-dock Staging  +  WMS Cross Dock created
├── Delivery Note     on_submit
│       └── deduct_location_qty → Staging location
└── Stock Entry       on_submit
        ├── _process_source → deduct from Staging (material issues / picks)
        └── _process_target
                ├── Normal output    → RECV
                └── Production return (Material Transfer + work_order)
                        → Inspection location

WMS DocTypes
├── WMS Zone                    (zone master per warehouse)
├── WMS Putaway Rule            (routing rules: customer+item → zone)
├── Storage Location            (physical bins with zone, capacity, type)
├── Batch Location Stock        (qty per item/batch/location/customer)
├── Batch Location Movement     (immutable audit trail)
├── Location Pick               (pick task — links multiple Pick Lists)
│       ├── Location Pick Source (child: linked Pick Lists)
│       └── Location Pick Line   (child: pick lines with Pick List ref)
├── WMS QC Check                (quality/quantity inspection document)
│       └── WMS QC Check Line   (child: per item outcome)
├── WMS Cross Dock              (cross-dock tracking document)
│       └── WMS Cross Dock Item (child: items + staging status)
├── WMS Cycle Count             (zone stock count document)
│       ├── WMS Cycle Count Zone (child: zones to count)
│       └── WMS Cycle Count Line (child: system vs counted qty)
└── WMS Settings                (global configuration — single doctype)

Client-side
├── Purchase Receipt  → cross-dock checkbox + SO suggestion dialog
├── Pick List form    → "WMS → Generate Location Pick" button
│       └── Strategy dialog + new / add-to-existing option
├── Batch Location Stock form
│       └── "Voorraad Verplaatsen" — putaway suggestion + compatibility check
├── Location Pick form → post-submit discrepancy dialog
├── WMS QC Check form → Start / submit flow
├── WMS Cross Dock form → "Gereed voor Verzending" button
└── WMS Cycle Count form → "Telregels Genereren" button
```

All qty mutations go through helpers in `events/utils.py`:

| Function | Action |
|---|---|
| `add_location_qty` | Create or increment BLS + write movement |
| `deduct_location_qty` | Reduce BLS (floor at 0) + write movement |
| `move_location_qty` | Atomic transfer between two locations + write movement |
| `evaluate_putaway_rule` | Find best zone + location for a batch via Putaway Rules |
| `iter_batch_entries` | Yield (batch_no, qty) — handles v15 and v16 bundle style |

---

## DocTypes

### WMS Zone
| Field | Description |
|---|---|
| `zone_code` | Unique code, e.g. `ZONE-JUMBO` |
| `zone_name` | Display name |
| `warehouse` | ERPNext Warehouse |
| `zone_type` | One of the 8 zone types |
| `dedicated_customer` | If set, zone is exclusive to this customer |
| `is_active` | Active/inactive |

### Storage Location
| Field | Description |
|---|---|
| `location_code` | Unique code, e.g. `A-1-2` |
| `warehouse` | ERPNext Warehouse |
| `zone` | Link to WMS Zone |
| `location_type` | Extended type (Receiving / Storage / Active Storage / QC Hold / etc.) |
| `pick_sequence` | Physical aisle sort order |
| `max_qty` | Capacity limit (0 = no limit) |
| `is_active` | Active/inactive |

### Batch Location Stock
| Field | Description |
|---|---|
| `item_code` | ERPNext Item |
| `batch_no` | ERPNext Batch |
| `warehouse` | ERPNext Warehouse |
| `storage_location` | Storage Location |
| `zone` | Fetched from storage_location.zone |
| `customer` | Owner of this stock (from Batch) |
| `qty` | Current quantity (never negative, never deleted) |
| `uom` | Unit of measure |

### Batch Location Movement
| Field | Description |
|---|---|
| `posting_date / time` | When the movement occurred |
| `item_code / batch_no` | What moved |
| `warehouse` | In which warehouse |
| `movement_type` | Inbound / Putaway / Pick / Cross-dock / QC Release / Production / Production Return / Cycle Count / Manual |
| `customer` | Whose stock moved |
| `from_location` | Source (null = inbound) |
| `to_location` | Destination (null = outbound) |
| `qty` | Quantity moved |
| `reference_doctype / name` | Linked source document |

### WMS Putaway Rule
| Field | Description |
|---|---|
| `priority` | Lower = evaluated first |
| `warehouse` | Scope to warehouse (empty = all) |
| `customer` | Match customer (empty = all) |
| `item_group` | Match item group (empty = all) |
| `target_zone` | Zone where matching items should go |
| `is_active` | Active/inactive |

### WMS QC Check
| Field | Description |
|---|---|
| `purchase_receipt` | Source PR |
| `warehouse` | Warehouse |
| `check_type` | Kwaliteit / Kwantiteit / Beide |
| `status` | Pending → In Progress → Completed |
| `items` | Child table: WMS QC Check Line |

**WMS QC Check Line:**  
`item_code | batch_no | from_location | received_qty | approved_qty | rejected_qty | outcome | quality_remarks`

### WMS Cross Dock
| Field | Description |
|---|---|
| `purchase_receipt` | Source PR |
| `customer` | Customer |
| `status` | Pending → Staged → Delivered |
| `items` | Child: WMS Cross Dock Item |

**WMS Cross Dock Item:**  
`item_code | batch_no | warehouse | xdock_location | sales_order | qty | staged_qty | delivered_qty`

### Location Pick
| Field | Description |
|---|---|
| `pick_lists` | Child table of linked Pick Lists (Location Pick Source) |
| `status` | Draft → Open → Completed / Cancelled |
| `picking_strategy` | Strategy used to generate lines |
| `picker` | Who is picking |

**Location Pick Line:**  
`pick_list | item_code | batch_no | warehouse | source_location | required_qty | picked_qty`

### WMS Cycle Count
| Field | Description |
|---|---|
| `count_date` | Date of count |
| `warehouse` | Warehouse |
| `count_zones` | Child: zones to count |
| `count_lines` | Child: WMS Cycle Count Line |
| `status` | Draft → In Progress → Completed |

**WMS Cycle Count Line:**  
`storage_location | zone | item_code | batch_no | customer | system_qty | counted_qty | difference | status`

### WMS Settings (Single DocType)
| Field | Description |
|---|---|
| `auto_create_on_receipt` | Auto-create BLS on Purchase Receipt submit |
| `validate_against_erpnext` | Block WMS qty exceeding ERPNext SLE qty |
| `default_putaway_mode` | Manual / Suggest / Enforce |
| `qc_trigger` | Per Receipt Line / Never |
| `auto_create_cross_dock` | Auto-detect cross-dock via PO→SO |

---

## Workflows

### Inbound – Standard Receipt

```
Supplier ships → Purchase Receipt submitted (ERPNext)
    ↓ [WMS event]
    ├── Putaway Rule evaluated → suggested location calculated
    ├── BLS created on RECV location
    └── customer written to Batch record (from wms_customer field)
```

Medewerker gebruikt "Voorraad Verplaatsen" vanuit de RECV record.  
Systeem toont putaway suggestie (aanbevolen zone + locatie).

---

### Inbound – QC Required

```
Purchase Receipt regel: wms_require_qc = 1
    ↓ [WMS event]
    ├── BLS created on QC Hold location (NOT RECV)
    └── WMS QC Check document auto-created (status: Pending)

Medewerker opent QC Check:
    ├── Vult check_type in (Kwaliteit / Kwantiteit / Beide)
    └── Per regel: approved_qty + rejected_qty + opmerkingen

WMS QC Check submit:
    ├── Approved qty → verplaatst van QC Hold → RECV (klaar voor putaway)
    └── Rejected qty → verplaatst van QC Hold → Quarantine
```

---

### Inbound – Cross-dock

**Automatisch** (PO → SO koppeling, `auto_create_cross_dock = 1`):
```
Purchase Receipt submitted
    ↓ WMS detecteert po_detail → sales_order link
    ├── BLS created on Cross-dock Staging (NOT RECV)
    └── WMS Cross Dock document auto-created
```

**Handmatig** (Purchase Receipt regel: `wms_cross_dock = 1`):
```
Medewerker vlagt cross-dock op PR-regel
    ↓ Systeem toont open Sales Orders voor dezelfde klant
    └── Medewerker kiest of bevestigt de SO
```

Beide situaties resulteren in een **WMS Cross Dock** document.  
"Gereed voor Verzending" knop → verplaatst van XDOCK → Outbound Staging → Delivery Note flow.

---

### Putaway – Move Stock

```
Open Batch Location Stock (RECV of QC-goedgekeurd)
    ↓ Klik "Voorraad Verplaatsen"
    ↓ Systeem berekent putaway suggestie:
        1. Zoek passende Putaway Rule (klant + warehouse)
        2. Voorkeur: locatie met al dezelfde klant (consolidatie)
        3. Daarna: lege locatie in de doelzone
    ↓ Dialoog toont aanbevolen locatie (medewerker kan afwijken)
    ↓ Compatibiliteitscheck:
        ├── Andere klant → geblokkeerd ❌
        ├── Zelfde klant, ander item → Ja/Nee bevestiging met overzicht
        └── Capaciteit overschreden → zachte waarschuwing
    ↓ Bevestigd → BLS bijgewerkt, Batch Location Movement geschreven
```

---

### Outbound – Sales Order to Delivery

```
Sales Order → Pick List (ERPNext) → Submit Pick List
    ↓ WMS knop: "Generate Location Pick"
    ├── Kies picking strategie (Pick Sequence / FEFO / FIFO)
    └── Kies: nieuwe Location Pick OF toevoegen aan bestaande open LP

Location Pick aangemaakt met regels per Pick List
    └── Picker vult picked_qty in per regel

Submit Location Pick:
    ├── Stock verplaatst: Storage → Outbound Staging
    ├── Batch Location Movement geschreven (movement_type: Pick)
    └── Post-submit dialoog: sync picked_qty naar Pick List? (Ja / Nee)

Delivery Note (ERPNext) ingediend:
    └── WMS trekt Outbound Staging af
```

---

### Manufacturing – Bulk Raw Material Picking

```
Work Order 1 + Work Order 2 (zelfde grondstof)
    ↓ ERPNext: Pick List PL-001 (WO-1) + Pick List PL-002 (WO-2)

Magazijnbeheer combineert:
    ↓ "Generate Location Pick" → kies PL-001 + PL-002 samen
    ↓ Location Pick: 10m stof voor PL-001, 15m stof voor PL-002

Picker pickt 25m totaal, vult picked_qty in

Submit Location Pick:
    └── 25m stof → Production Staging locatie

Productie verwerkt WO-001:
    └── Stock Entry (Material Transfer for Manufacture) → WMS trekt 10m af van Staging

Productie verwerkt WO-002:
    └── Stock Entry → WMS trekt 15m af van Staging (totaal 0m)
```

---

### Production Return – Inspection Zone

```
Resterend materiaal terug van productie
    ↓ Stock Entry (Material Transfer, work_order ingevuld)
    ↓ [WMS event: stock_entry._process_target]
    └── target warehouse heeft Inspection locatie
        → materiaal gaat naar Inspection (NIET naar RECV)

Magazijnbeheer evalueert:
    ├── Goed materiaal → "Voorraad Verplaatsen" → opslag
    └── Beschadigd materiaal → "Voorraad Verplaatsen" → Quarantine
```

---

### Cycle Counting

```
Magazijnbeheer maakt WMS Cycle Count aan:
    └── Kiest warehouse + zones

Klik "Telregels Genereren":
    └── Systeem vult alle BLS-records in met systeem-hoeveelheid

Medewerker telt fysiek:
    └── Vult counted_qty in per regel (verschil zichtbaar in real-time)

WMS Cycle Count indienen:
    ├── Afwijkingen worden automatisch toegepast op BLS
    └── Batch Location Movement geschreven (movement_type: Cycle Count)
```

---

## Picking Strategies

| Strategy | Sort Logic |
|---|---|
| **Pick Sequence** | `pick_sequence` ASC, grootste qty eerst — volgt fysieke looproute |
| **FEFO – First Expired, First Out** | `Batch.expiry_date` ASC — batches zonder vervaldatum gaan als laatste |
| **FIFO – First In, First Out** | `Batch.creation` ASC — oudste batch eerst |

Alle strategieën verdelen qty automatisch over meerdere locaties als één locatie niet voldoende heeft.

---

## Customer Segregation

WMS dwingt klantscheiding af op **opslaglocaties** (type: Storage / Active Storage).

| Situatie | Resultaat |
|---|---|
| Locatie leeg | ✅ Altijd toegestaan |
| Zelfde klant, zelfde item | ✅ Toegestaan |
| Zelfde klant, ander item | ✅ Toegestaan — Ja/Nee bevestiging met overzicht |
| Andere klant | ❌ Geblokkeerd |
| Klant vs eigen voorraad | ❌ Geblokkeerd |

**Transit-locaties** (QC Hold, Inspection, Cross-dock, Quarantine, Staging) zijn vrijgesteld van klantscheiding — daar mogen meerdere klanten naast elkaar staan.

De klant wordt automatisch opgepikt van het Batch-record. Op de Purchase Receipt regel is een `Customer (WMS)` veld beschikbaar; bij submit wordt deze klant naar het Batch-record geschreven zodat alle toekomstige bewegingen de klant automatisch kennen.

---

## ERPNext v16 Compatibility

ERPNext v16 introduced **Serial and Batch Bundle** — batch info is no longer on the transaction row directly but in a linked child table.

**`iter_batch_entries(item)`** handles both:
1. Checks `item.serial_and_batch_bundle` (in memory)
2. Falls back to a DB read if not populated during `on_submit`
3. Reads `Serial and Batch Entry` rows → yields `(batch_no, qty)`
4. Falls back to `item.batch_no` for v15-style rows

**`_get_pl_item_batch_no(pl_item)`** (used in `generate_location_pick`):
1. Checks `pl_item.batch_no` directly (v15)
2. Resolves `serial_and_batch_bundle` → first `Serial and Batch Entry` row (v16)

**`picked_qty` on Pick List Item:**  
In v16, ERPNext auto-sets `picked_qty = qty` on Pick List submit. WMS does **not** touch this during Location Pick submit. A post-submit dialog lets the user optionally overwrite it with WMS actuals.

---

## Configuration

### 1. WMS Settings
**WMS → Setup → WMS Settings**

| Setting | Recommended |
|---|---|
| Auto Create on Receipt | ✅ Enabled |
| Validate Against ERPNext | ✅ Enabled |
| Putaway Mode | Suggest |
| QC Trigger | Per Receipt Line |
| Auto-detect Cross-dock | ✅ Enabled |

### 2. WMS Zones
**WMS → Setup → WMS Zone → + New** — maak zones aan per warehouse:

```
Code          | Naam                  | Type               | Klant
--------------|-----------------------|--------------------|--------
RECV-ZONE     | Ontvangst             | Receiving          |
ZONE-JUMBO    | Opslag Jumbo          | Active Storage     | Jumbo
ZONE-AH       | Opslag Albert Heijn   | Active Storage     | Albert Heijn
ZONE-OWN      | Eigen Voorraad        | Active Storage     |
QC-ZONE       | Kwaliteitscontrole    | QC Hold            |
PROD-STAGE    | Productie Staging     | Production Staging |
OUT-STAGE     | Uitlevering Staging   | Outbound Staging   |
XDOCK-ZONE    | Cross-dock            | Cross-dock Staging |
INSP-ZONE     | Inspectie             | Inspection         |
QUAR-ZONE     | Quarantaine           | Quarantine         |
```

### 3. Storage Locations
**WMS → Storage Location → + New** per fysiek vak:

```
Code     | Zone         | Type              | Pick Seq | Max Qty
---------|--------------|-------------------|----------|---------
RECV     | RECV-ZONE    | Receiving         | 0        |
A-1-1    | ZONE-JUMBO   | Active Storage    | 10       | 500
A-1-2    | ZONE-JUMBO   | Active Storage    | 20       | 500
B-1-1    | ZONE-AH      | Active Storage    | 10       | 500
QC-HOLD  | QC-ZONE      | QC Hold           | 0        |
STAGING  | OUT-STAGE    | Outbound Staging  | 0        |
PROD-STG | PROD-STAGE   | Production Staging| 0        |
XDOCK    | XDOCK-ZONE   | Cross-dock Staging| 0        |
INSPECT  | INSP-ZONE    | Inspection        | 0        |
QUARANT  | QUAR-ZONE    | Quarantine        | 0        |
```

### 4. Putaway Rules
**WMS → Setup → WMS Putaway Rule → + New**:

```
Prioriteit | Warehouse | Klant         | Artikelgroep | Doelzone
-----------|-----------|---------------|--------------|----------
1          | Magazijn  | Jumbo         |              | ZONE-JUMBO
2          | Magazijn  | Albert Heijn  |              | ZONE-AH
10         | Magazijn  |               | Grondstoffen | PROD-STAGE
99         | Magazijn  |               |              | ZONE-OWN
```

### 5. Item Setup
All WMS-tracked items must have **Has Batch No = 1** in the ERPNext Item master.

---

## Installation

```bash
# 1. Get the app
bench get-app https://github.com/Mikado331909/frappe_wms

# 2. Install on your site
bench --site [your-site-name] install-app frappe_wms

# 3. Run migrations
bench --site [your-site-name] migrate
```

### After Installation
1. Configure **WMS Settings**
2. Create **WMS Zones** for your warehouse layout
3. Create **Storage Locations** and link them to zones
4. Configure **WMS Putaway Rules** (customer → zone)
5. Hard-refresh the browser (`Ctrl+Shift+R`)

### Upgrading from an earlier version
```bash
bench update --pull
bench --site [your-site-name] migrate
```

---

## Reports

| Report | Description |
|---|---|
| **Zone Occupancy** | Bezettingsgraad per zone (huidige voorraad vs capaciteit %) |
| **Customer Stock Overview** | Voorraad per klant per zone per artikel |
| **Pick Performance** | Gepickt vs vereist per picker per periode, met afwijkingen |
| **Inbound Outbound Volume** | Bewegingsvolume per dag per bewegingstype |
| **Location Pick Lines** | Dagelijks pickoverzicht — alle pickregels met status |
| **Location Stock Reconciliation** | WMS qty vs ERPNext SLE qty — discrepanties signaleren |

---

## Design Decisions

### Never-delete BLS records
`Batch Location Stock` records are never deleted. Zero-qty records remain for audit history — same pattern as ERPNext's own `Bin` doctype.

### ERPNext owns qty, WMS owns location
WMS tracks *where* stock is. ERPNext tracks *how much* exists. Any discrepancy is surfaced via the reconciliation report and resolved by the warehouse team — WMS never silently overrides ERPNext.

### Customer segregation on storage, not transit
Active storage locations enforce one-customer-per-location. Transit locations (QC Hold, Inspection, Cross-dock, Staging, Quarantine) are exempt — goods from multiple customers can pass through simultaneously.

### Event-driven, non-intrusive
WMS reacts to standard ERPNext document events (`on_submit`, `on_cancel`). It does not override ERPNext core methods, bypass the stock ledger, or interfere with standard workflows.

### Warehouse-scoped activation
WMS activates per warehouse based on whether Storage Locations are configured. Warehouses without WMS locations are silently skipped, enabling selective deployment (e.g. raw materials only).

### WMS does not own `picked_qty`
In ERPNext v16, `Pick List Item.picked_qty` is managed by ERPNext's Serial and Batch Bundle system. WMS offers an optional post-submit dialog to sync it, rather than silently overwriting.

---

## License

MIT
