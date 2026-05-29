# Frappe WMS

A lightweight **Warehouse Management System (WMS)** layer for ERPNext v16.  
Adds bin-level location tracking on top of ERPNext's standard warehouse/batch stock — without replacing any core ERPNext behaviour.

---

## Table of Contents

1. [Overview](#overview)
2. [Key Concepts](#key-concepts)
3. [Architecture](#architecture)
4. [DocTypes](#doctypes)
5. [Workflows](#workflows)
   - [Inbound – Purchase Receipt](#inbound--purchase-receipt)
   - [Putaway – Move Stock](#putaway--move-stock)
   - [Outbound – Sales Order to Delivery](#outbound--sales-order-to-delivery)
   - [Manufacturing – Raw Material Picking](#manufacturing--raw-material-picking)
6. [Picking Strategies](#picking-strategies)
7. [ERPNext v16 Compatibility](#erpnext-v16-compatibility)
8. [Configuration](#configuration)
9. [Installation](#installation)
10. [Reports](#reports)
11. [Design Decisions](#design-decisions)

---

## Overview

Frappe WMS tracks **where exactly** items sit within an ERPNext warehouse (row, shelf, bin) and **manages the physical pick flow** from storage location → picking staging area → delivery.

**What it does:**
- Tracks batch stock per physical storage location (bin, shelf, rack)
- Automatically creates location stock records on Purchase Receipt
- Generates Location Pick documents from ERPNext Pick Lists with FIFO / FEFO / Pick Sequence strategies
- Moves stock to a Picking Staging location on Location Pick submit
- Deducts staging stock when a Delivery Note is submitted
- Records every stock movement in an immutable audit trail

**What it does NOT do:**
- Replace ERPNext's own stock ledger — ERPNext remains the source of truth for quantities
- Manage serial numbers (batch tracking only)
- Handle non-batch-tracked items (all items must use ERPNext batch tracking)

**Supported ERPNext versions:** v16 (also backward-compatible with v15 batch field style)

---

## Key Concepts

### Storage Location
A physical location inside a warehouse — e.g. rack A, row 1, bin 2 → `A-1-2`.  
Each Storage Location belongs to one ERPNext Warehouse and has a **type**:

| Type | Purpose |
|---|---|
| `Receiving` (RECV) | Items land here after a Purchase Receipt |
| `Storage` | Normal picking locations (racks, bins, shelves) |
| `Picking Staging` | Items wait here after picking, ready for shipment |

### Batch Location Stock (BLS)
The core record: `item_code + batch_no + warehouse + storage_location → qty`.  
**Records are never deleted** — zero-quantity records remain for a complete history (same pattern as ERPNext's own `Bin` doctype).

### Batch Location Movement
An immutable audit log entry created for every qty change.  
Every `add`, `deduct`, or `move` operation writes one movement record.

### Location Pick
A WMS-native document generated from an ERPNext Pick List.  
Lists which items to pick, from which locations, in which quantities.  
On submit: moves stock from Storage → Picking Staging.

---

## Architecture

```
ERPNext Events (hooks)
├── Purchase Receipt  on_submit / on_cancel
│       └── add_location_qty → BLS (RECV location)
├── Delivery Note     on_submit
│       └── deduct_location_qty → BLS (Staging location)
└── Stock Entry       on_submit
        ├── _process_source → deduct from Staging (material issues)
        └── _process_target → add to RECV (production output)

WMS DocTypes
├── Storage Location      (warehouse bin/shelf master)
├── Batch Location Stock  (qty per item/batch/location)
├── Batch Location Movement (audit trail)
├── Location Pick         (pick task document)
│       └── Location Pick Line (child table)
└── WMS Settings          (global configuration)

Client-side
├── Pick List form  → "WMS → Generate Location Pick" button
│       └── Strategy dialog (Pick Sequence / FEFO / FIFO)
├── Batch Location Stock form → "Move Stock" button
└── Location Pick form  → post-submit discrepancy dialog
```

All WMS quantity mutations go through a single set of helpers in `events/utils.py`:

| Function | Action |
|---|---|
| `add_location_qty` | Create or increment a BLS record |
| `deduct_location_qty` | Reduce a BLS record (floor at 0) |
| `move_location_qty` | Atomic transfer between two locations |
| `iter_batch_entries` | Yield (batch_no, qty) — handles v15 and v16 bundle style |

---

## DocTypes

### Storage Location
| Field | Description |
|---|---|
| `name` | Location code, e.g. `A-1-2` |
| `warehouse` | Linked ERPNext Warehouse |
| `location_type` | `Receiving` / `Storage` / `Picking Staging` |
| `pick_sequence` | Sort order used by Pick Sequence strategy |
| `is_active` | Active/inactive toggle |

### Batch Location Stock
| Field | Description |
|---|---|
| `item_code` | ERPNext Item |
| `batch_no` | ERPNext Batch |
| `warehouse` | ERPNext Warehouse |
| `storage_location` | Storage Location |
| `qty` | Current quantity (never negative, never deleted) |
| `uom` | Unit of measure |

### Batch Location Movement
| Field | Description |
|---|---|
| `posting_date / time` | When the movement occurred |
| `item_code / batch_no` | What moved |
| `warehouse` | In which warehouse |
| `from_location` | Source (null = inbound) |
| `to_location` | Destination (null = outbound) |
| `qty` | Quantity moved |
| `reference_doctype / name` | Linked source document (PR, DN, SE, Location Pick) |

### Location Pick
| Field | Description |
|---|---|
| `pick_list` | Linked ERPNext Pick List |
| `status` | Open → Completed / Cancelled |
| `picking_strategy` | Strategy used to generate lines |
| `posting_date / time` | Pick date |
| `picker` | Optional: who picked |

**Location Pick Line (child)**

| Field | Description |
|---|---|
| `item_code / batch_no` | What to pick |
| `warehouse` | From which warehouse |
| `source_location` | Physical bin to pick from |
| `required_qty` | Qty to be picked |
| `picked_qty` | Qty actually picked (filled in by warehouse worker) |
| `pick_list_item` | Link back to Pick List Item row |

### WMS Settings (Single DocType)
| Field | Description |
|---|---|
| `auto_create_on_receipt` | Create BLS automatically on Purchase Receipt submit |

---

## Workflows

### Inbound – Purchase Receipt

```
Supplier ships goods
    ↓
ERPNext Purchase Receipt (submit)
    ↓  [WMS event: purchase_receipt.on_submit]
Batch Location Stock created / updated
    └── location_type = Receiving  (e.g. RECV)
    └── qty = received quantity per batch
```

**Condition:** Only runs if the destination warehouse has an active `Receiving` Storage Location AND `WMS Settings.auto_create_on_receipt = 1`.

**On cancel:** The BLS qty is deducted (record remains at 0 — never deleted).

---

### Putaway – Move Stock

After goods arrive in RECV they are physically moved to a storage bin.

```
Open Batch Location Stock (RECV record)
    ↓ Click "Move Stock"
Dialog: choose destination Storage Location + qty
    ↓ [API: batch_location_stock.move_stock]
RECV qty reduced → destination BLS created/updated
Batch Location Movement recorded
```

---

### Outbound – Sales Order to Delivery

```
Sales Order
    ↓ Create → Pick List (ERPNext)
    ↓ Submit Pick List
WMS button: "Generate Location Pick"
    ↓ Choose picking strategy
    ↓ [API: generate_location_pick]
Location Pick (Draft)
    ├── Lines: item / batch / source_location / required_qty
    └── Picker sets picked_qty per line
    ↓ Submit Location Pick
    ├── Stock moved: Storage Location → Picking Staging [move_location_qty]
    ├── Batch Location Movement recorded
    └── Post-submit dialog: sync picked_qty to Pick List? (Yes / No)
    ↓ Create Delivery Note from Pick List (ERPNext)
    ↓ Submit Delivery Note
    └── [WMS event: delivery_note.on_submit]
        └── Staging qty deducted [deduct_location_qty]
```

---

### Manufacturing – Raw Material Picking

```
Sales Order → Work Order (ERPNext)
    ↓ Create → Pick List (purpose: Material Transfer for Manufacture)
    ↓ Submit Pick List
WMS button: "Generate Location Pick"
    ↓ Same flow as outbound picking
Location Pick submit
    └── Raw materials: Storage → Picking Staging
    ↓ Create Stock Entry (Material Transfer for Manufacture) from Pick List
    ↓ Submit Stock Entry
    └── [WMS event: stock_entry._process_source]
        └── Staging qty deducted
```

**Note for production companies:** WMS only needs to track **raw materials** in storage locations. Finished goods that go directly from production to a packing department do not need WMS location tracking. Simply do not create any Storage Locations for the finished goods warehouse — WMS will silently skip that warehouse entirely.

---

## Picking Strategies

When generating a Location Pick, the user selects a strategy via a dialog:

| Strategy | Sort Logic |
|---|---|
| **Pick Sequence** | `Storage Location.pick_sequence` ASC, largest qty first — follows your physical aisle order |
| **FEFO – First Expired, First Out** | `Batch.expiry_date` ASC — batches with no expiry date go last |
| **FIFO – First In, First Out** | `Batch.creation` ASC — oldest batch first |

All strategies allocate qty across as many locations as needed to satisfy the required quantity, splitting across bins automatically if one bin does not have enough stock.

---

## ERPNext v16 Compatibility

ERPNext v16 introduced **Serial and Batch Bundle** — batch/serial information is no longer stored directly on transaction item rows but in a linked child table (`Serial and Batch Entry`).

Frappe WMS handles both styles transparently:

**`iter_batch_entries(item)`** — used in all event handlers:
1. Checks `item.serial_and_batch_bundle` (in memory)
2. Falls back to a DB read if not yet populated during `on_submit`
3. Reads `Serial and Batch Entry` rows to get `(batch_no, qty)` pairs
4. Falls back to `item.batch_no` for v15-style rows

**`_get_pl_item_batch_no(pl_item)`** — used in `generate_location_pick`:
1. Checks `pl_item.batch_no` directly (v15)
2. Resolves `serial_and_batch_bundle` → first `Serial and Batch Entry` row (v16)

**`picked_qty` on Pick List Item:**  
In v16, ERPNext automatically sets `picked_qty = qty` on Pick List submit as part of the bundle creation process. WMS does **not** touch this field during Location Pick submit to avoid double-counting. Instead, a post-submit dialog gives the user the option to overwrite `picked_qty` with the actual WMS-confirmed quantity — useful when a picker picks fewer items than planned.

---

## Configuration

### 1. WMS Settings
Navigate to **WMS → Setup → WMS Settings**:
- Enable **Auto Create on Receipt** to automatically create BLS records when a Purchase Receipt is submitted.

### 2. Storage Locations
Navigate to **WMS → Storage Location → + New** for each physical bin/shelf:

```
Example setup for warehouse "Finished Goods - CRINGS":

Name     | Type             | Pick Sequence | Active
---------|------------------|---------------|-------
RECV     | Receiving        | 0             | ✓
STAGING  | Picking Staging  | 0             | ✓
A-1-1    | Storage          | 10            | ✓
A-1-2    | Storage          | 20            | ✓
A-2-1    | Storage          | 30            | ✓
```

> **Tip:** WMS only activates for warehouses that have at least one active Storage Location configured. Warehouses without Storage Locations are silently skipped. This makes it easy to deploy WMS selectively — for example, only for raw materials warehouses in a manufacturing company.

### 3. Item Setup
All WMS-tracked items must have **Has Batch No = 1** in the ERPNext Item master. WMS does not support non-batch-tracked items.

---

## Installation

```bash
# 1. Get the app
bench get-app https://github.com/Mikado331909/frappe_wms

# 2. Install on your site
bench --site [your-site-name] install-app frappe_wms

# 3. Run migrations (creates DocTypes, runs patches, loads fixtures)
bench --site [your-site-name] migrate
```

### After Installation
1. Open **WMS Settings** and enable `Auto Create on Receipt`
2. Create **Storage Locations** for each WMS-managed warehouse (RECV, STAGING, and your storage bins)
3. Hard-refresh the browser (`Ctrl+Shift+R`) — the WMS sidebar section should appear

---

## Reports

### Location Pick Lines
Full list of all Location Pick Line records with item, batch, source location, required qty, and picked qty. Use for a daily picking overview or to check pick progress.

### Location Stock Reconciliation
Shows current WMS qty per storage location alongside ERPNext's warehouse-level qty — useful for identifying discrepancies between the two systems.

---

## Design Decisions

### Never-delete BLS records
`Batch Location Stock` records are never deleted. When qty reaches 0, the record remains with `qty = 0`. This mirrors ERPNext's own `Bin` doctype behaviour and prevents cascading link-checker errors when `Batch Location Movement` audit records reference the BLS document.

### WMS does not own `picked_qty`
In ERPNext v16, `Pick List Item.picked_qty` is managed by ERPNext's Serial and Batch Bundle system. WMS offers an optional post-submit confirmation dialog to sync it — rather than silently overwriting — giving the user full control over what ERPNext sees.

### Event-driven, not intrusive
WMS reacts to standard ERPNext document events (`on_submit`, `on_cancel`). It does not override any ERPNext core methods, bypass ERPNext's own stock ledger, or interfere with standard ERPNext workflows.

### Warehouse-scoped activation
WMS activates per warehouse based on whether that warehouse has Storage Locations configured. This means you can run WMS for some warehouses and not others within the same ERPNext instance — useful for multi-company setups or gradual rollouts.

---

## License

MIT
