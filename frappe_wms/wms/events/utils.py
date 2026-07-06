"""
Shared helpers for all WMS event handlers.

Rules
-----
* Every qty change to Batch Location Stock must produce a Batch Location Movement row.
* These functions are the only permitted writers of Batch Location Stock rows.
* `raise_if_missing=False` lets callers skip silently for non-WMS warehouses.
* Customer segregation is enforced on Storage / Active Storage locations only.
  Transit locations (QC Hold, Inspection, Cross-dock, etc.) allow mixed customers.

ERPNext v16 note
----------------
v16 tracks batches via "Serial and Batch Bundle" (child: "Serial and Batch Entry")
instead of a direct batch_no field on transaction items. Use
`iter_batch_entries(item)` to transparently handle both old and new style.
"""

import frappe
from frappe import _
from frappe.utils import nowdate, nowtime, flt


# ---------------------------------------------------------------------------
# Location types where customer segregation is not enforced (transit zones)
# ---------------------------------------------------------------------------

_TRANSIT_LOCATION_TYPES = frozenset({
    "Receiving",
    "Picking Staging",
    "Outbound Staging",
    "QC Hold",
    "Production Staging",
    "Cross-dock Staging",
    "Inspection",
    "Quarantine",
})

# ---------------------------------------------------------------------------
# ERPNext v16 Serial and Batch Bundle helper
# ---------------------------------------------------------------------------


def iter_batch_entries(item):
    """
    Yield (batch_no, qty) pairs for a transaction item row.
    Handles ERPNext v15 (direct batch_no) and v16 (Serial and Batch Bundle).
    """
    bundle = getattr(item, "serial_and_batch_bundle", None)
    if not bundle and getattr(item, "name", None) and getattr(item, "doctype", None):
        bundle = frappe.db.get_value(item.doctype, item.name, "serial_and_batch_bundle")

    if bundle:
        entries = frappe.db.get_all(
            "Serial and Batch Entry",
            filters={"parent": bundle},
            fields=["batch_no", "qty"],
        )
        for e in entries:
            if e.batch_no and flt(e.qty) != 0:
                yield e.batch_no, abs(flt(e.qty))
    elif getattr(item, "batch_no", None):
        # Legacy path: always yield in STOCK UOM, like bundle entries do.
        # item.qty is in the transaction UOM (e.g. Box), while the stock
        # ledger and Batch Location Stock track stock UOM (e.g. Nos).
        stock_qty = flt(getattr(item, "stock_qty", 0))
        if not stock_qty:
            stock_qty = flt(item.qty) * (flt(getattr(item, "conversion_factor", 0)) or 1.0)
        yield item.batch_no, stock_qty


# ---------------------------------------------------------------------------
# Location lookup helpers
# ---------------------------------------------------------------------------


def _get_location_by_type(warehouse, location_type, raise_if_missing=True):
    loc = frappe.db.get_value(
        "Storage Location",
        {"warehouse": warehouse, "location_type": location_type, "is_active": 1},
        "name",
        order_by="pick_sequence asc",
    )
    if not loc and raise_if_missing:
        frappe.throw(
            _("No active {0} location found for warehouse {1}.").format(
                location_type, warehouse
            )
        )
    return loc


def get_receiving_location(warehouse, raise_if_missing=True):
    return _get_location_by_type(warehouse, "Receiving", raise_if_missing)


def get_picking_staging_location(warehouse, raise_if_missing=True):
    # Supports both the old ("Picking Staging") and new ("Outbound Staging") name
    loc = _get_location_by_type(warehouse, "Picking Staging", raise_if_missing=False)
    if not loc:
        loc = _get_location_by_type(warehouse, "Outbound Staging", raise_if_missing=False)
    if not loc and raise_if_missing:
        frappe.throw(
            _("No active Picking Staging / Outbound Staging location found for warehouse {0}.").format(warehouse)
        )
    return loc


def get_qc_hold_location(warehouse, raise_if_missing=True):
    return _get_location_by_type(warehouse, "QC Hold", raise_if_missing)


def get_inspection_location(warehouse, raise_if_missing=True):
    return _get_location_by_type(warehouse, "Inspection", raise_if_missing)


def get_cross_dock_location(warehouse, raise_if_missing=True):
    return _get_location_by_type(warehouse, "Cross-dock Staging", raise_if_missing)


def get_quarantine_location(warehouse, raise_if_missing=True):
    return _get_location_by_type(warehouse, "Quarantine", raise_if_missing)


def get_production_staging_location(warehouse, raise_if_missing=True):
    return _get_location_by_type(warehouse, "Production Staging", raise_if_missing)


# ---------------------------------------------------------------------------
# Putaway Rule evaluation
# ---------------------------------------------------------------------------


def evaluate_putaway_rule(warehouse, customer, item_code=None):
    """
    Evaluate putaway rules and return the best zone and location suggestion.

    Returns:
        dict {"zone": ..., "location": ..., "reason": ...} or None
    """
    rules = frappe.db.get_all(
        "WMS Putaway Rule",
        filters={"is_active": 1},
        fields=["priority", "customer", "item_group", "target_zone", "warehouse"],
        order_by="priority asc",
    )

    item_group = frappe.db.get_value("Item", item_code, "item_group") if item_code else None

    for rule in rules:
        # Warehouse filter (empty means all warehouses)
        if rule.warehouse and rule.warehouse != warehouse:
            continue
        # Customer filter
        if rule.customer and rule.customer != (customer or ""):
            continue
        # Item group filter
        if rule.item_group and rule.item_group != (item_group or ""):
            continue

        # Rule matches - find the best location in the target zone
        location = _find_best_location_in_zone(rule.target_zone, customer)
        if location:
            return {
                "zone": rule.target_zone,
                "location": location,
                "reason": _("Putaway Rule: {0} -> zone {1}").format(
                    ("customer " + customer) if customer else "company stock",
                    rule.target_zone,
                ),
            }

    return None


def _find_best_location_in_zone(zone, customer):
    """
    Find the best location in a zone.
    Prefer locations that already contain stock for the same customer.
    Then use empty active locations in the zone.
    """
    # 1. Consolidation: location with the same customer
    consolidation = frappe.db.sql("""
        SELECT DISTINCT bls.storage_location
        FROM `tabBatch Location Stock` bls
        INNER JOIN `tabStorage Location` sl ON sl.name = bls.storage_location
        WHERE sl.zone = %s
          AND (bls.customer = %s OR (%s IS NULL AND (bls.customer IS NULL OR bls.customer = '')))
          AND bls.qty > 0
          AND sl.is_active = 1
          AND sl.location_type IN ('Storage', 'Active Storage')
        ORDER BY sl.pick_sequence ASC
        LIMIT 1
    """, (zone, customer or "", customer))

    if consolidation:
        return consolidation[0][0]

    # 2. Empty location in the zone
    empty = frappe.db.sql("""
        SELECT sl.name
        FROM `tabStorage Location` sl
        WHERE sl.zone = %s
          AND sl.is_active = 1
          AND sl.location_type IN ('Storage', 'Active Storage')
          AND NOT EXISTS (
              SELECT 1 FROM `tabBatch Location Stock` bls
              WHERE bls.storage_location = sl.name AND bls.qty > 0
          )
        ORDER BY sl.pick_sequence ASC
        LIMIT 1
    """, zone)

    return empty[0][0] if empty else None


# ---------------------------------------------------------------------------
# Customer validation
# ---------------------------------------------------------------------------


def _get_customer_for_batch(batch_no):
    """Resolve the customer linked to a batch."""
    if not batch_no:
        return None
    return frappe.db.get_value("Batch", batch_no, "customer") or None


def _validate_customer_on_location(storage_location, customer):
    """
    Block adding stock to a storage location that already contains another customer.
    Transit locations (QC Hold, Inspection, etc.) are skipped.
    """
    loc_type = frappe.db.get_value("Storage Location", storage_location, "location_type") or ""
    if loc_type in _TRANSIT_LOCATION_TYPES:
        return  # Transit zones do not need customer segregation

    existing_rows = frappe.db.get_all(
        "Batch Location Stock",
        filters={"storage_location": storage_location, "qty": [">", 0]},
        fields=["customer"],
        distinct=True,
    )
    if not existing_rows:
        return

    for row in existing_rows:
        existing_customer = row.customer or None
        if existing_customer != customer:
            frappe.throw(
                _(
                    "Location {0} already contains stock for {1}. "
                    "Choose another location for {2}."
                ).format(
                    storage_location,
                    ("customer " + existing_customer) if existing_customer else "company stock",
                    ("customer " + customer) if customer else "company stock",
                )
            )


# ---------------------------------------------------------------------------
# Locking helpers
# ---------------------------------------------------------------------------


def _lock_storage_locations(*storage_locations):
    """
    Serialize WMS stock mutations per physical location.

    Locking the Storage Location rows prevents two concurrent requests from
    creating or updating Batch Location Stock rows for the same location at the
    same time. Locations are sorted to keep multi-location moves deadlock-safe.
    """
    locations = tuple(sorted({loc for loc in storage_locations if loc}))
    if not locations:
        return

    frappe.db.sql(
        """
        SELECT name
        FROM `tabStorage Location`
        WHERE name IN %(locations)s
        ORDER BY name
        FOR UPDATE
        """,
        {"locations": locations},
    )


def _get_location_stock_for_update(item_code, batch_no, warehouse, storage_location):
    rows = frappe.db.sql(
        """
        SELECT name, qty, customer
        FROM `tabBatch Location Stock`
        WHERE item_code = %(item_code)s
          AND batch_no = %(batch_no)s
          AND warehouse = %(warehouse)s
          AND storage_location = %(storage_location)s
        FOR UPDATE
        """,
        {
            "item_code": item_code,
            "batch_no": batch_no,
            "warehouse": warehouse,
            "storage_location": storage_location,
        },
        as_dict=True,
    )
    return rows[0] if rows else None


def _check_erpnext_ceiling(item_code, batch_no, warehouse, add_qty):
    """
    Enforce that total WMS location qty never exceeds the ERPNext stock
    ledger qty for the same item + batch + warehouse.

    Runs inside add_location_qty *after* the location lock is taken, so it is
    race-safe per location. Controlled by WMS Settings.validate_against_erpnext.
    (The Document-level validation in Batch Location Stock is bypassed by the
    helpers via db.set_value / ignore_validate, so the check must live here.)
    """
    if not frappe.db.get_single_value("WMS Settings", "validate_against_erpnext"):
        return

    from frappe_wms.wms.doctype.batch_location_stock.batch_location_stock import (
        _get_erpnext_batch_qty,
    )

    erpnext_qty = _get_erpnext_batch_qty(item_code, batch_no, warehouse)
    current_total = flt(
        frappe.db.sql(
            """
            SELECT COALESCE(SUM(qty), 0)
            FROM `tabBatch Location Stock`
            WHERE item_code = %s AND batch_no = %s AND warehouse = %s
            """,
            (item_code, batch_no, warehouse),
        )[0][0]
    )

    if current_total + flt(add_qty) > erpnext_qty + 0.001:
        frappe.throw(
            _(
                "Adding {0} would raise total location qty to {1} for Item {2}, "
                "Batch {3}, Warehouse {4}, exceeding ERPNext stock of {5}."
            ).format(
                flt(add_qty, 3),
                flt(current_total + flt(add_qty), 3),
                item_code,
                batch_no,
                warehouse,
                flt(erpnext_qty, 3),
            )
        )


# ---------------------------------------------------------------------------
# Qty mutations
# ---------------------------------------------------------------------------


def add_location_qty(
    item_code, batch_no, warehouse, storage_location, qty, uom,
    ref_doctype, ref_name, movement_type=None,
):
    """Create or increment a Batch Location Stock row and record the movement."""
    qty = flt(qty)
    if qty <= 0:
        return

    _lock_storage_locations(storage_location)
    customer = _get_customer_for_batch(batch_no)
    _validate_customer_on_location(storage_location, customer)
    _check_erpnext_ceiling(item_code, batch_no, warehouse, qty)

    existing = _get_location_stock_for_update(
        item_code, batch_no, warehouse, storage_location
    )

    if existing:
        frappe.db.set_value("Batch Location Stock", existing.name, "qty", flt(existing.qty) + qty)
    else:
        if not uom:
            uom = frappe.db.get_value("Item", item_code, "stock_uom")
        doc = frappe.get_doc({
            "doctype": "Batch Location Stock",
            "item_code": item_code,
            "batch_no": batch_no,
            "warehouse": warehouse,
            "storage_location": storage_location,
            "qty": qty,
            "uom": uom,
            "customer": customer,
        })
        doc.flags.ignore_validate = True
        doc.insert(ignore_permissions=True)

    _record_movement(
        item_code=item_code,
        batch_no=batch_no,
        warehouse=warehouse,
        from_location=None,
        to_location=storage_location,
        qty=qty,
        ref_doctype=ref_doctype,
        ref_name=ref_name,
        customer=customer,
        movement_type=movement_type or "Inbound",
    )


def deduct_location_qty(
    item_code, batch_no, warehouse, storage_location, qty,
    ref_doctype, ref_name, movement_type=None,
):
    """Reduce a Batch Location Stock row and record the movement."""
    qty = flt(qty)
    if qty <= 0:
        return

    _lock_storage_locations(storage_location)
    existing = _get_location_stock_for_update(
        item_code, batch_no, warehouse, storage_location
    )

    if not existing:
        frappe.throw(
            _(
                "No Batch Location Stock found for Item {0}, Batch {1}, "
                "Warehouse {2}, Location {3}."
            ).format(item_code, batch_no, warehouse, storage_location)
        )

    new_qty = flt(existing.qty) - qty
    if new_qty < -0.001:
        frappe.throw(
            _(
                "Cannot deduct {0} from location {1}: only {2} available "
                "for Item {3} Batch {4}."
            ).format(
                flt(qty, 3), storage_location, flt(existing.qty, 3), item_code, batch_no,
            )
        )

    _record_movement(
        item_code=item_code,
        batch_no=batch_no,
        warehouse=warehouse,
        from_location=storage_location,
        to_location=None,
        qty=qty,
        ref_doctype=ref_doctype,
        ref_name=ref_name,
        customer=existing.customer,
        movement_type=movement_type or "Pick",
    )

    frappe.db.set_value("Batch Location Stock", existing.name, "qty", max(new_qty, 0.0))


def move_location_qty(
    item_code, batch_no, warehouse, from_location, to_location, qty,
    ref_doctype, ref_name, movement_type=None,
):
    """Atomically move qty between two locations in the same warehouse."""
    qty = flt(qty)
    if qty <= 0:
        return
    if from_location == to_location:
        return

    _lock_storage_locations(from_location, to_location)
    customer = _get_customer_for_batch(batch_no)
    _validate_customer_on_location(to_location, customer)

    src = _get_location_stock_for_update(
        item_code, batch_no, warehouse, from_location
    )
    if not src:
        frappe.throw(
            _("No stock on location {0} for Item {1} Batch {2}.").format(
                from_location, item_code, batch_no
            )
        )
    if flt(src.qty) < qty - 0.001:
        frappe.throw(
            _(
                "Insufficient stock on {0}: available {1}, requested {2} "
                "for Item {3} Batch {4}."
            ).format(from_location, flt(src.qty, 3), flt(qty, 3), item_code, batch_no)
        )

    remaining = flt(src.qty) - qty

    dst = _get_location_stock_for_update(
        item_code, batch_no, warehouse, to_location
    )
    if dst:
        frappe.db.set_value("Batch Location Stock", dst.name, "qty", flt(dst.qty) + qty)
    else:
        uom = frappe.db.get_value("Item", item_code, "stock_uom")
        new_doc = frappe.get_doc({
            "doctype": "Batch Location Stock",
            "item_code": item_code,
            "batch_no": batch_no,
            "warehouse": warehouse,
            "storage_location": to_location,
            "qty": qty,
            "uom": uom,
            "customer": customer,
        })
        new_doc.flags.ignore_validate = True
        new_doc.insert(ignore_permissions=True)

    _record_movement(
        item_code=item_code,
        batch_no=batch_no,
        warehouse=warehouse,
        from_location=from_location,
        to_location=to_location,
        qty=qty,
        ref_doctype=ref_doctype,
        ref_name=ref_name,
        customer=customer,
        movement_type=movement_type or "Putaway",
    )

    frappe.db.set_value("Batch Location Stock", src.name, "qty", max(remaining, 0.0))


# ---------------------------------------------------------------------------
# Reversal by replay
# ---------------------------------------------------------------------------


def reverse_reference_movements(ref_doctype, ref_name):
    """
    Reverse every Batch Location Movement created by a reference document,
    in reverse chronological order.

    This replaces heuristic cancel logic ("the stock *should* still be at
    RECV") with an exact replay of what actually happened:
      * add    (None -> loc)  becomes a deduct from loc
      * deduct (loc -> None)  becomes an add back to loc
      * move   (a -> b)       becomes a move b -> a

    If stock has since moved on and a reversal cannot be fully applied, the
    reversal is capped at the available qty and the shortfall is reported
    loudly instead of silently ignored.
    """
    movements = frappe.db.get_all(
        "Batch Location Movement",
        filters={
            "reference_doctype": ref_doctype,
            "reference_name": ref_name,
            "movement_type": ["!=", "Reversal"],
        },
        fields=[
            "name", "item_code", "batch_no", "warehouse",
            "from_location", "to_location", "qty",
        ],
        order_by="creation desc, name desc",
    )

    shortfalls = []

    for m in movements:
        qty = flt(m.qty)
        if qty <= 0:
            continue

        if m.from_location and m.to_location:
            available = _get_available_qty(
                m.item_code, m.batch_no, m.warehouse, m.to_location
            )
            reversal_qty = min(qty, available)
            if qty - reversal_qty > 0.001:
                shortfalls.append(
                    _("{0} / batch {1}: {2} of {3} could not be moved back from {4}").format(
                        m.item_code, m.batch_no,
                        flt(qty - reversal_qty, 3), flt(qty, 3), m.to_location,
                    )
                )
            if reversal_qty > 0.001:
                move_location_qty(
                    item_code=m.item_code,
                    batch_no=m.batch_no,
                    warehouse=m.warehouse,
                    from_location=m.to_location,
                    to_location=m.from_location,
                    qty=reversal_qty,
                    ref_doctype=ref_doctype,
                    ref_name=ref_name,
                    movement_type="Reversal",
                )

        elif m.to_location:
            available = _get_available_qty(
                m.item_code, m.batch_no, m.warehouse, m.to_location
            )
            reversal_qty = min(qty, available)
            if qty - reversal_qty > 0.001:
                shortfalls.append(
                    _("{0} / batch {1}: {2} of {3} no longer available at {4}").format(
                        m.item_code, m.batch_no,
                        flt(qty - reversal_qty, 3), flt(qty, 3), m.to_location,
                    )
                )
            if reversal_qty > 0.001:
                deduct_location_qty(
                    item_code=m.item_code,
                    batch_no=m.batch_no,
                    warehouse=m.warehouse,
                    storage_location=m.to_location,
                    qty=reversal_qty,
                    ref_doctype=ref_doctype,
                    ref_name=ref_name,
                    movement_type="Reversal",
                )

        elif m.from_location:
            add_location_qty(
                item_code=m.item_code,
                batch_no=m.batch_no,
                warehouse=m.warehouse,
                storage_location=m.from_location,
                qty=qty,
                uom=None,
                ref_doctype=ref_doctype,
                ref_name=ref_name,
                movement_type="Reversal",
            )

    if shortfalls:
        message = _(
            "WMS location stock was only partially reversed because stock "
            "has moved on since {0} {1} was submitted:"
        ).format(_(ref_doctype), ref_name)
        details = "<br>".join(frappe.utils.escape_html(s) for s in shortfalls)
        frappe.log_error(
            title=f"WMS partial reversal: {ref_doctype} {ref_name}",
            message="\n".join(shortfalls),
        )
        frappe.msgprint(
            f"{message}<br>{details}",
            title=_("Partial WMS Reversal"),
            indicator="orange",
        )


def _get_available_qty(item_code, batch_no, warehouse, storage_location):
    return flt(
        frappe.db.get_value(
            "Batch Location Stock",
            {
                "item_code": item_code,
                "batch_no": batch_no,
                "warehouse": warehouse,
                "storage_location": storage_location,
            },
            "qty",
        )
        or 0.0
    )


# ---------------------------------------------------------------------------
# Internal audit writer
# ---------------------------------------------------------------------------


def _record_movement(
    item_code, batch_no, warehouse, from_location, to_location, qty,
    ref_doctype, ref_name, customer=None, movement_type=None,
):
    frappe.get_doc({
        "doctype": "Batch Location Movement",
        "posting_date": nowdate(),
        "posting_time": nowtime(),
        "item_code": item_code,
        "batch_no": batch_no,
        "warehouse": warehouse,
        "from_location": from_location,
        "to_location": to_location,
        "qty": qty,
        "reference_doctype": ref_doctype,
        "reference_name": ref_name,
        "customer": customer,
        "movement_type": movement_type,
    }).insert(ignore_permissions=True)
