# Frappe WMS

Frappe WMS is a Warehouse Management System layer for ERPNext. It adds physical location control, putaway, picking, quality checks, cross-docking, cycle counting, WMS dashboards and operational reports on top of ERPNext's standard stock ledger.

The app is built around one simple split:

- ERPNext remains the source of truth for stock ledger entries, valuation, batches, purchasing, sales, manufacturing and accounting.
- Frappe WMS tracks where stock is physically located inside a warehouse: zone, storage location, batch, customer and quantity.
- Every WMS stock movement creates a `Batch Location Movement` audit record.
- The app is intended for batch-tracked inventory. It reads ERPNext v16 Serial and Batch Bundles, but it does not provide a full serial-number location workflow.

The app targets ERPNext/Frappe version 16 and keeps compatibility with older direct `batch_no` transaction rows where possible.

---

## Contents

1. [What This App Solves](#what-this-app-solves)
2. [Core Principles](#core-principles)
3. [Module And Workspace](#module-and-workspace)
4. [Architecture](#architecture)
5. [Data Model](#data-model)
6. [ERPNext Integrations](#erpnext-integrations)
7. [Workflows](#workflows)
8. [Picking Strategies](#picking-strategies)
9. [Customer Segregation](#customer-segregation)
10. [Configuration](#configuration)
11. [Example Setup](#example-setup)
12. [Dashboards And Reports](#dashboards-and-reports)
13. [Installation](#installation)
14. [Upgrade And Migration](#upgrade-and-migration)
15. [Validation And Testing](#validation-and-testing)
16. [Translations](#translations)
17. [Limitations And Notes](#limitations-and-notes)
18. [Technical Structure](#technical-structure)
19. [Developer Notes](#developer-notes)
20. [License](#license)

---

## What This App Solves

ERPNext knows how much stock exists in a warehouse. Warehouse teams often also need to know:

- which zone a batch is in;
- which physical storage location contains a batch;
- which customer owns or controls a batch;
- whether goods are in receiving, QC, cross-dock, inspection, production staging or outbound staging;
- which stock has already been physically picked;
- what differences were found during a cycle count;
- whether WMS location totals still match ERPNext stock ledger quantities.

Frappe WMS provides this operational layer without replacing ERPNext inventory accounting.

### Main Capabilities

- WMS workspace with shortcuts, KPI cards and a dashboard chart.
- Warehouse zones such as Receiving, Active Storage, QC Hold, Production Staging and Outbound Staging.
- Physical Storage Locations within zones.
- Batch Location Stock per item, batch, warehouse, location and customer.
- Batch Location Movement as the audit trail for every physical movement.
- Automatic handling of Purchase Receipt, Delivery Note and Stock Entry events.
- QC flow with WMS QC Check.
- Cross-dock flow with WMS Cross Dock.
- Location Pick flow generated from ERPNext Pick List.
- Putaway suggestions based on WMS Putaway Rules.
- Customer segregation on storage locations.
- Cycle counting by warehouse zone.
- Reports for occupancy, customer stock, pick performance, movement volume and reconciliation.

### What The App Does Not Replace

- ERPNext Stock Ledger Entry remains the source of truth for financial and administrative stock.
- ERPNext Warehouse remains the administrative warehouse level.
- ERPNext Item, Batch, Purchase Receipt, Pick List, Delivery Note and Stock Entry remain standard documents.
- The app does not implement a full serial-number WMS.
- The app does not create stock valuation postings outside ERPNext.

---

## Core Principles

### ERPNext Owns Quantity And Value

Frappe WMS owns physical location detail. ERPNext owns the stock ledger. WMS should not silently correct ERPNext. Any mismatch should be visible in the Location Stock Reconciliation report.

### Location Stock Is Not Deleted

`Batch Location Stock` records are kept even when quantity becomes zero. This preserves history and avoids losing the operational trail.

### Every Movement Is Audited

Adding, deducting or moving WMS stock should go through shared helpers in `events/utils.py`. Those helpers always create a `Batch Location Movement` row.

### Batch Tracking Is Required

The core WMS key is:

```text
item_code + batch_no + warehouse + storage_location
```

Items managed by WMS should therefore use batch tracking in ERPNext.

### Warehouses Can Be Activated Gradually

A warehouse participates in WMS when active Storage Locations are configured for it. Warehouses without WMS locations are skipped by event handlers where possible, which allows phased rollout.

---

## Module And Workspace

The app registers a `WMS` module.

| Item | Value |
|---|---|
| App name | `frappe_wms` |
| Module | `WMS` |
| App home | `/desk/wms` |
| Workspace route | `/desk/wms` |
| Workspace document | `WMS` |
| Workspace export | `frappe_wms/wms/workspace/wms/wms.json` |

The app also ships a Dashboard record named `WMS`, so it appears under Build > Dashboard. The dashboard uses the same operational cards and chart as the workspace:

- Pending QC Checks
- Cross-dock Pending
- Active Storage Locations
- Warehouse Movements by Type

---

## Architecture

Frappe WMS is event-driven. It reacts to standard ERPNext documents instead of replacing them.

```text
ERPNext Purchase Receipt
  -> on_submit
     -> standard receipt to Receiving
     -> QC receipt to QC Hold + WMS QC Check
     -> cross-dock receipt to Cross-dock Staging + WMS Cross Dock

ERPNext Pick List
  -> form button
     -> Generate Location Pick
     -> WMS reads Batch Location Stock on storage locations
     -> WMS creates Location Pick lines

Location Pick
  -> submit
     -> move picked quantity from storage to Outbound/Picking Staging

ERPNext Delivery Note
  -> on_submit
     -> deduct stock from Outbound/Picking Staging

ERPNext Stock Entry
  -> on_submit
     -> source side deducts from staging
     -> target side receives into Receiving or Inspection

WMS Cycle Count
  -> generate count lines from Batch Location Stock
  -> submit applies WMS location corrections and writes audit movements
```

### Shared Stock Helpers

Shared helpers live in `frappe_wms/wms/events/utils.py`.

| Helper | Purpose |
|---|---|
| `iter_batch_entries` | Reads batches from ERPNext v16 Serial and Batch Bundle or older direct batch fields. |
| `get_receiving_location` | Finds an active Receiving location for a warehouse. |
| `get_picking_staging_location` | Finds a Picking Staging or Outbound Staging location. |
| `get_qc_hold_location` | Finds a QC Hold location. |
| `get_cross_dock_location` | Finds a Cross-dock Staging location. |
| `get_quarantine_location` | Finds a Quarantine location. |
| `get_production_staging_location` | Finds a Production Staging location. |
| `evaluate_putaway_rule` | Determines the best zone and location from WMS Putaway Rules. |
| `add_location_qty` | Creates or increases Batch Location Stock and writes a movement. |
| `deduct_location_qty` | Decreases Batch Location Stock and writes a movement. |
| `move_location_qty` | Moves stock between two locations and writes a movement. |

---

## Data Model

### WMS Zone

A WMS Zone groups physical locations inside an ERPNext warehouse.

| Field | Type | Purpose |
|---|---|---|
| `zone_code` | Data | Unique zone code. |
| `zone_name` | Data | Human-readable zone name. |
| `warehouse` | Link | ERPNext Warehouse. |
| `zone_type` | Select | Operational zone type. |
| `dedicated_customer` | Link | Optional customer reserved for the zone. |
| `is_active` | Check | Enables or disables the zone. |

Zone types:

- Receiving
- Active Storage
- QC Hold
- Production Staging
- Outbound Staging
- Cross-dock Staging
- Inspection
- Quarantine

Example:

```text
zone_code: ZONE-A
zone_name: Storage Zone A
warehouse: WH-01
zone_type: Active Storage
dedicated_customer: Customer A
is_active: 1
```

### Storage Location

A Storage Location is a physical bin, shelf, rack position, pallet position or staging area.

| Field | Type | Purpose |
|---|---|---|
| `location_code` | Data | Location code. |
| `location_name` | Data | Human-readable location name. |
| `warehouse` | Link | ERPNext Warehouse. |
| `zone` | Link | WMS Zone. |
| `location_type` | Select | Operational use of the location. |
| `pick_sequence` | Int | Route order for picking. |
| `max_qty` | Float | Capacity; zero means no fixed limit. |
| `is_active` | Check | Enables or disables the location. |

### Batch Location Stock

This is the core WMS location stock record. It describes how much of a batch is present at a physical location.

| Field | Type | Purpose |
|---|---|---|
| `item_code` | Link | ERPNext Item. |
| `item_name` | Data | Item name. |
| `batch_no` | Link | ERPNext Batch. |
| `customer` | Link | Customer or owner for the batch. |
| `zone` | Link | WMS Zone. |
| `warehouse` | Link | ERPNext Warehouse. |
| `storage_location` | Link | Physical storage location. |
| `qty` | Float | Current WMS location quantity. |
| `uom` | Link | Unit of measure. |
| `reserved_qty` | Float | Reserved quantity for later expansion. |

Validations:

- The Storage Location must belong to the same warehouse.
- A duplicate row for the same item, batch, warehouse and location is not allowed.
- If `validate_against_erpnext` is enabled, total WMS location quantity for item/batch/warehouse may not exceed ERPNext stock quantity.

### Batch Location Movement

This is the operational audit log.

| Field | Type | Purpose |
|---|---|---|
| `posting_date` | Date | Movement date. |
| `posting_time` | Time | Movement time. |
| `item_code` | Link | ERPNext Item. |
| `batch_no` | Link | ERPNext Batch. |
| `movement_type` | Select | Type of movement. |
| `customer` | Link | Customer or batch owner. |
| `warehouse` | Link | ERPNext Warehouse. |
| `from_location` | Link | Source location. |
| `to_location` | Link | Target location. |
| `qty` | Float | Movement quantity. |
| `reference_doctype` | Link | Source document type. |
| `reference_name` | Dynamic Link | Source document. |
| `remarks` | Small Text | Optional remark. |

Movement types:

- Inbound
- Putaway
- Pick
- Cross-dock
- QC Release
- Production
- Production Return
- Cycle Count
- Manual

### WMS Putaway Rule

Putaway Rules determine the target zone for received stock.

| Field | Type | Purpose |
|---|---|---|
| `priority` | Int | Lowest number is evaluated first. |
| `warehouse` | Link | Optional warehouse filter. |
| `customer` | Link | Optional customer match. |
| `item_group` | Link | Optional item group match. |
| `target_zone` | Link | Target WMS Zone. |
| `is_active` | Check | Enables or disables the rule. |

Rule evaluation:

1. Sort active rules by priority.
2. Match warehouse if filled.
3. Match customer if filled.
4. Match item group if filled.
5. Use the target zone.
6. Prefer a location that already contains stock for the same customer.
7. Otherwise choose an empty active storage location.

### Location Pick

Location Pick is the WMS picking document generated from one or more ERPNext Pick Lists.

Important fields:

- `pick_lists`: linked ERPNext Pick Lists.
- `status`: Draft, Open, Completed or Cancelled.
- `picking_strategy`: Pick Sequence, FEFO or FIFO.
- `picker`: user who is picking.
- `items`: Location Pick Line child table.

Each Location Pick Line stores item, batch, warehouse, source location, required quantity, picked quantity, UOM and the ERPNext Pick List Item row id.

### WMS QC Check

WMS QC Check is used when received goods must be inspected before putaway.

Important fields:

- `purchase_receipt`
- `warehouse`
- `check_type`: Quality, Quantity or Both
- `status`: Pending, In Progress or Completed
- `inspector`
- `check_date`
- `items`: WMS QC Check Line child table

Each QC line stores received quantity, approved quantity, rejected quantity and outcome.

### WMS Cross Dock

WMS Cross Dock tracks goods that should flow directly from receipt to outbound staging.

Important fields:

- `purchase_receipt`
- `customer`
- `status`: Pending, Staged, Delivered or Cancelled
- `posting_date`
- `items`: WMS Cross Dock Item child table
- `notes`

### WMS Cycle Count

WMS Cycle Count supports physical counts by zone.

Important fields:

- `count_date`
- `warehouse`
- `status`: Draft, In Progress, Completed or Cancelled
- `counted_by`
- `count_zones`
- `count_lines`

Submitting a cycle count adjusts WMS location stock and writes `Cycle Count` movement records.

### WMS Settings

Single DocType for global WMS settings.

| Field | Purpose |
|---|---|
| `auto_create_on_receipt` | Automatically create WMS location stock when submitting a Purchase Receipt. |
| `validate_against_erpnext` | Validate WMS location quantity against ERPNext stock. |
| `default_putaway_mode` | Manual, Suggest or Enforce. |
| `qc_trigger` | Per Receipt Line or Never. |
| `auto_create_cross_dock` | Detect cross-dock from ERPNext links where possible. |

---

## ERPNext Integrations

### Custom Fields

The app adds fields to ERPNext documents.

On `Batch`:

| Field | Type | Purpose |
|---|---|---|
| `customer` | Link Customer | Customer that owns or controls the batch for WMS segregation. |

On `Purchase Receipt Item`:

| Field | Type | Purpose |
|---|---|---|
| `wms_customer` | Link Customer | Customer or owner for this receipt line. |
| `wms_require_qc` | Check | Send this receipt line to QC Hold. |
| `wms_cross_dock` | Check | Send this receipt line to Cross-dock Staging. |
| `wms_cross_dock_so` | Link Sales Order | Optional Sales Order for cross-dock. |

### Purchase Receipt

On submit:

- If `auto_create_on_receipt` is disabled, WMS does nothing.
- WMS reads batch rows with `iter_batch_entries`.
- `wms_customer` is copied to the Batch if the Batch has no customer yet.
- Cross-dock takes priority over QC.
- Cross-dock lines go to Cross-dock Staging.
- QC lines go to QC Hold.
- Standard lines go to Receiving.
- QC creates a `WMS QC Check`.
- Cross-dock creates a `WMS Cross Dock`.

On cancel, WMS attempts to reverse the earlier receipt from the expected WMS location and never deducts more than is still available.

### Pick List

The app adds a client-side button to ERPNext Pick List:

```text
WMS -> Generate Location Pick
```

The user selects a picking strategy and either creates a new Location Pick or appends to an existing open Location Pick.

### Delivery Note

On Delivery Note submit, WMS finds staging stock and deducts available staged quantity. The movement type is `Pick`.

### Stock Entry

On Stock Entry submit, the source side deducts from staging if staged stock exists. The target side adds stock to Receiving. Production returns with `Material Transfer` and `work_order` are routed to Inspection when possible.

---

## Workflows

### Standard Inbound Receipt

```text
Purchase Receipt submit
  -> WMS reads batch entries
  -> WMS sets customer on Batch if wms_customer is filled
  -> WMS finds Receiving location
  -> WMS creates or increases Batch Location Stock
  -> WMS writes Batch Location Movement with movement_type Inbound
```

Example:

```text
Item: ITEM-A
Batch: BATCH-001
Warehouse: WH-01
Receiving location: RECV-01
Qty: 100
Customer: Customer A
```

### QC Receipt

```text
Purchase Receipt Item: wms_require_qc = 1
  -> WMS finds QC Hold location
  -> stock is received into QC Hold
  -> WMS QC Check is created
```

Then:

```text
WMS QC Check
  -> user enters approved_qty and rejected_qty
  -> submit
     -> approved_qty to Receiving
     -> rejected_qty to Quarantine
```

### Cross-dock Receipt

```text
Purchase Receipt Item:
  wms_cross_dock = 1
  wms_cross_dock_so = SO-0001
```

Flow:

```text
Purchase Receipt submit
  -> WMS finds Cross-dock Staging location
  -> WMS places stock on the cross-dock location
  -> WMS Cross Dock document is created
```

Then:

```text
WMS Cross Dock
  -> button Ready to Ship
  -> WMS moves available qty from Cross-dock Staging to Outbound/Picking Staging
```

### Putaway

```text
Open Batch Location Stock in Receiving
  -> click Move Stock
  -> WMS fetches putaway suggestion
  -> user chooses target location
  -> WMS checks compatibility
  -> WMS moves stock and writes movement
```

Compatibility checks:

- Different customer on storage location: blocked.
- Same customer with existing stock: warning and confirmation.
- Capacity exceeded: warning.

### Outbound Picking

```text
ERPNext Pick List
  -> WMS Generate Location Pick
  -> select picking strategy
  -> WMS creates Location Pick
```

On Location Pick submit:

```text
Location Pick submit
  -> WMS checks that picked_qty is available
  -> WMS moves picked_qty to Outbound/Picking Staging
  -> status becomes Completed
```

### Delivery Note

```text
Delivery Note submit
  -> WMS finds Outbound/Picking Staging
  -> WMS deducts available staged qty
  -> movement_type Pick
```

### Cycle Count

```text
WMS Cycle Count
  -> choose warehouse
  -> add zones
  -> click Generate Count Lines
  -> WMS fills count_lines from Batch Location Stock
  -> user enters counted_qty
  -> submit
```

On submit:

- Positive difference increases Batch Location Stock.
- Negative difference decreases Batch Location Stock.
- Movement type is `Cycle Count`.
- Lines are marked `Corrected`.

---

## Picking Strategies

| Strategy | Sort Logic |
|---|---|
| Pick Sequence | `Storage Location.pick_sequence` ascending, then largest available quantity. |
| FEFO - First Expired, First Out | Batch expiry date ascending, empty expiry dates last, then pick sequence. |
| FIFO - First In, First Out | Batch creation ascending, then pick sequence. |

Example:

```text
Demand: 80 units of ITEM-A batch BATCH-001

Available:
  A-01-01: 30
  A-01-02: 70

Result:
  Pick line 1: A-01-01, 30
  Pick line 2: A-01-02, 50
```

---

## Customer Segregation

Customer segregation prevents stock from different customers from being mixed on the same storage location.

This check applies to:

- Storage
- Active Storage

This check does not apply to transit locations:

- Receiving
- Picking Staging
- Outbound Staging
- QC Hold
- Production Staging
- Cross-dock Staging
- Inspection
- Quarantine

Rules:

| Situation | Result |
|---|---|
| Location is empty | Allowed. |
| Same customer, same item | Allowed. |
| Same customer, different item | Allowed after warning. |
| Different customer | Blocked. |
| Company stock mixed with customer stock | Blocked. |

---

## Configuration

### Step 1: WMS Settings

Open:

```text
WMS -> WMS Settings
```

Recommended starting values:

| Setting | Value |
|---|---|
| Auto-create Location Stock on Purchase Receipt | Enabled |
| Validate WMS Stock against ERPNext Stock | Enabled |
| Putaway Mode | Suggest |
| QC Trigger | Per Receipt Line |
| Auto-detect Cross-dock via PO to SO link | Enabled if cross-dock is used |

### Step 2: Create Zones

Recommended base setup:

| Zone | Type | Purpose |
|---|---|---|
| RECV-ZONE | Receiving | Incoming goods. |
| STORAGE-A | Active Storage | Normal storage. |
| QC-ZONE | QC Hold | Goods waiting for inspection. |
| OUT-STAGE | Outbound Staging | Picked goods waiting for shipment. |
| XDOCK-ZONE | Cross-dock Staging | Goods that flow directly to outbound. |
| INSP-ZONE | Inspection | Returns or inspection stock. |
| QUAR-ZONE | Quarantine | Rejected or blocked goods. |

### Step 3: Create Storage Locations

Every WMS warehouse needs at least one active Receiving location if inbound automation should work.

| Location | Type | Zone | Pick sequence |
|---|---|---|---|
| RECV-01 | Receiving | RECV-ZONE | 0 |
| A-01-01 | Active Storage | STORAGE-A | 10 |
| A-01-02 | Active Storage | STORAGE-A | 20 |
| QC-01 | QC Hold | QC-ZONE | 0 |
| OUT-01 | Outbound Staging | OUT-STAGE | 0 |
| XDOCK-01 | Cross-dock Staging | XDOCK-ZONE | 0 |
| INSP-01 | Inspection | INSP-ZONE | 0 |
| QUAR-01 | Quarantine | QUAR-ZONE | 0 |

### Step 4: Create Putaway Rules

Example rules:

| Priority | Warehouse | Customer | Item Group | Target Zone |
|---|---|---|---|---|
| 1 | WH-01 | Customer A |  | STORAGE-A |
| 2 | WH-01 | Customer B |  | STORAGE-B |
| 10 | WH-01 |  | Raw Materials | STORAGE-RAW |
| 99 | WH-01 |  |  | STORAGE-GENERAL |

Blank fields act as wildcards.

---

## Example Setup

This example uses generic names only.

```text
Warehouse:
  WH-01

Zones:
  RECV-ZONE       Receiving
  STORAGE-A       Active Storage
  STORAGE-B       Active Storage
  QC-ZONE         QC Hold
  OUT-STAGE       Outbound Staging
  XDOCK-ZONE      Cross-dock Staging
  INSP-ZONE       Inspection
  QUAR-ZONE       Quarantine

Locations:
  RECV-01         Receiving             RECV-ZONE
  A-01-01         Active Storage        STORAGE-A
  A-01-02         Active Storage        STORAGE-A
  B-01-01         Active Storage        STORAGE-B
  QC-01           QC Hold               QC-ZONE
  OUT-01          Outbound Staging      OUT-STAGE
  XDOCK-01        Cross-dock Staging    XDOCK-ZONE
  INSP-01         Inspection            INSP-ZONE
  QUAR-01         Quarantine            QUAR-ZONE

Items:
  ITEM-A          Batch tracked item
  ITEM-B          Batch tracked item

Batches:
  BATCH-001       Batch for ITEM-A
  BATCH-002       Batch for ITEM-B

Customers:
  Customer A
  Customer B
```

---

## Dashboards And Reports

The WMS workspace shows:

- shortcuts for Location Pick, Batch Location Stock, Storage Location and WMS Cycle Count;
- KPI cards for QC, cross-dock and active locations;
- chart `Warehouse Movements by Type`;
- link cards for Operations, Stock & Locations, Setup and Reports.

Reports:

| Report | Purpose |
|---|---|
| Zone Occupancy | Occupancy per zone based on locations, capacity and current stock. |
| Customer Stock Overview | Stock per customer, zone, warehouse, item, batch and location. |
| Pick Performance | Required versus picked quantities per Location Pick and picker. |
| Inbound Outbound Volume | Movements by date, warehouse, movement type and customer. |
| Location Pick Lines | Detailed overview of all Location Pick lines. |
| Location Stock Reconciliation | Compares ERPNext stock with WMS location stock per item, batch and warehouse. |

---

## Installation

For a normal bench installation:

```bash
bench get-app <repository-url>
bench --site <site-name> install-app frappe_wms
bench --site <site-name> migrate
```

For Frappe Cloud:

1. Add the app to the site.
2. Confirm that the correct branch and commit are active.
3. Deploy the app.
4. Run migrate.
5. Hard-refresh the browser with `Ctrl+Shift+R`.
6. Open `/desk/wms`.

After installation:

1. Open WMS Settings.
2. Create WMS Zones.
3. Create Storage Locations.
4. Create Putaway Rules.
5. Confirm that the WMS workspace is visible.
6. Test with a small Purchase Receipt and batch.

---

## Upgrade And Migration

After updating the app:

```bash
bench --site <site-name> migrate
bench --site <site-name> clear-cache
```

Important patches:

```text
frappe_wms.patches.v1_1.normalize_wms_v16_app_routing
frappe_wms.patches.v1_2.translate_wms_sources_to_english
```

The v1.2 translation patch:

- maps old Dutch QC select values to English values;
- updates existing Custom Field labels and descriptions;
- clears cache after migration.

---

## Validation And Testing

Minimum functional test:

1. Create `WH-01`.
2. Create Receiving, Active Storage, Outbound Staging, QC Hold, Cross-dock Staging and Quarantine locations.
3. Enable WMS Settings.
4. Create batch-tracked item `ITEM-A`.
5. Submit a Purchase Receipt with batch `BATCH-001`.
6. Check Batch Location Stock on Receiving.
7. Move stock to Active Storage.
8. Create Pick List.
9. Generate Location Pick.
10. Fill picked_qty.
11. Submit Location Pick.
12. Check stock on Outbound/Picking Staging.
13. Submit Delivery Note.
14. Confirm that staging stock was deducted.
15. Open Location Stock Reconciliation.

Developer checks:

```bash
python -m py_compile frappe_wms/hooks.py frappe_wms/wms/events/utils.py
python -m py_compile frappe_wms/wms/doctype/location_pick/location_pick.py
python -m py_compile frappe_wms/wms/doctype/batch_location_stock/batch_location_stock.py
```

If a bench test site is available:

```bash
bench --site <test-site> run-tests --app frappe_wms
```

---

## Translations

The app uses English as the source language. This is the normal pattern for Frappe apps: DocType labels, report labels, Python messages and JavaScript messages should be written in English and wrapped in translation functions where relevant.

Frappe chooses translations from the active language context:

1. request `_lang` parameter;
2. preferred language cookie for guests;
3. request `Accept-Language` for guests;
4. the logged-in user's language;
5. System Settings language;
6. fallback to English.

App translations live in:

```text
frappe_wms/translations/<language-code>.csv
```

Examples:

```text
frappe_wms/translations/nl.csv
frappe_wms/translations/de.csv
frappe_wms/translations/fr.csv
```

Each CSV row maps an English source string to a translated string:

```csv
Move Stock,<translated Move Stock>
Ready to Ship,<translated Ready to Ship>
Generate Count Lines,<translated Generate Count Lines>
```

The repository includes `translations/nl.csv` and `translations/fr.csv` as initial translation baselines. Additional languages can be added by creating another CSV file with the same source strings and translated values.

Developer rules for new UI text:

- Write new source text in English.
- Use `_("Message")` in Python.
- Use `__("Message")` in JavaScript.
- Keep DocType labels, report labels and fixture labels in English.
- Add translations to `translations/<language-code>.csv` for languages that should be supported.
- Run migrate and clear cache after changing labels or translations.

---

## Limitations And Notes

- ERPNext v16 Serial and Batch Bundle is read to find batch information. The app does not maintain a separate serial-number location stock model.
- Cycle Count adjusts `Batch Location Stock`. Financial inventory corrections must still be handled through ERPNext.
- `default_putaway_mode` contains Manual, Suggest and Enforce. The current UI mainly uses suggestions and confirmation checks.
- `auto_create_cross_dock` exists as a setting. Purchase Receipt logic detects cross-dock mainly through manual fields or existing PO/SO links.
- Without active Storage Locations per warehouse, WMS intentionally skips some event actions.
- The current app does not define a complete custom role model. Access is managed through standard Frappe/ERPNext permissions on DocTypes and reports.

---

## Technical Structure

Important files and folders:

```text
frappe_wms/
  hooks.py
  modules.txt
  patches.txt
  translations/
    nl.csv
  config/
    desktop.py
  fixtures/
    custom_field.json
    dashboard.json
    dashboard_chart.json
    number_card.json
    workspace.json
  public/
    images/
      frappe-wms-logo.svg
    js/
      batch_location_stock.js
      batch_location_stock_list.js
      location_pick.js
      pick_list.js
      purchase_receipt.js
      wms_cross_dock.js
      wms_cycle_count.js
      wms_qc_check.js
  patches/
    v1_0/
    v1_1/
    v1_2/
  wms/
    events/
      delivery_note.py
      purchase_receipt.py
      stock_entry.py
      utils.py
    doctype/
      batch_location_movement/
      batch_location_stock/
      location_pick/
      storage_location/
      wms_cross_dock/
      wms_cycle_count/
      wms_putaway_rule/
      wms_qc_check/
      wms_settings/
      wms_zone/
    report/
      customer_stock_overview/
      inbound_outbound_volume/
      location_pick_lines/
      location_stock_reconciliation/
      pick_performance/
      zone_occupancy/
    workspace/
      wms/
        wms.json
```

---

## Developer Notes

Use these rules for future development:

- Keep source strings in English.
- Wrap Python UI strings in `_()`.
- Wrap JavaScript UI strings in `__()`.
- Write stock mutations through `add_location_qty`, `deduct_location_qty` or `move_location_qty`.
- Do not directly update `Batch Location Stock.qty` outside controlled migrations.
- Always write a movement audit.
- Keep ERPNext stock ledger authoritative.
- Test with ERPNext v16 Serial and Batch Bundle.

---

## License

MIT
