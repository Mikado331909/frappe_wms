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
# Locatietypes waar klant-segregatie NIET geldt (transit zones)
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
        yield item.batch_no, flt(item.qty)


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
            _("Geen actieve {0} locatie gevonden voor warehouse {1}.").format(
                location_type, warehouse
            )
        )
    return loc


def get_receiving_location(warehouse, raise_if_missing=True):
    return _get_location_by_type(warehouse, "Receiving", raise_if_missing)


def get_picking_staging_location(warehouse, raise_if_missing=True):
    # Ondersteunt zowel oude ("Picking Staging") als nieuwe ("Outbound Staging") naam
    loc = _get_location_by_type(warehouse, "Picking Staging", raise_if_missing=False)
    if not loc:
        loc = _get_location_by_type(warehouse, "Outbound Staging", raise_if_missing=False)
    if not loc and raise_if_missing:
        frappe.throw(
            _("Geen actieve Picking Staging / Outbound Staging locatie gevonden voor warehouse {0}.").format(warehouse)
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
# Putaway Rule evaluatie
# ---------------------------------------------------------------------------


def evaluate_putaway_rule(warehouse, customer, item_code=None):
    """
    Evalueer putaway regels en geef beste zone + locatie suggestie terug.

    Returns:
        dict {"zone": ..., "location": ..., "reason": ...}  of  None
    """
    rules = frappe.db.get_all(
        "WMS Putaway Rule",
        filters={"is_active": 1},
        fields=["priority", "customer", "item_group", "target_zone", "warehouse"],
        order_by="priority asc",
    )

    item_group = frappe.db.get_value("Item", item_code, "item_group") if item_code else None

    for rule in rules:
        # Warehouse filter (leeg = geldt voor alle warehouses)
        if rule.warehouse and rule.warehouse != warehouse:
            continue
        # Customer filter
        if rule.customer and rule.customer != (customer or ""):
            continue
        # Item group filter
        if rule.item_group and rule.item_group != (item_group or ""):
            continue

        # Regel komt overeen — zoek beste locatie in de doelzone
        location = _find_best_location_in_zone(rule.target_zone, customer)
        if location:
            return {
                "zone": rule.target_zone,
                "location": location,
                "reason": _("Putaway Rule: {0} → zone {1}").format(
                    ("klant " + customer) if customer else "eigen voorraad",
                    rule.target_zone,
                ),
            }

    return None


def _find_best_location_in_zone(zone, customer):
    """
    Zoek de beste locatie in een zone.
    Voorkeur: locaties die al voorraad van dezelfde klant hebben (consolidatie).
    Daarna: lege actieve locaties in de zone.
    """
    # 1. Consolidatie: locatie met dezelfde klant
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

    # 2. Lege locatie in de zone
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
# Klant-validatie
# ---------------------------------------------------------------------------


def _get_customer_for_batch(batch_no):
    """Resolve the customer linked to a batch."""
    if not batch_no:
        return None
    return frappe.db.get_value("Batch", batch_no, "customer") or None


def _validate_customer_on_location(storage_location, customer):
    """
    Blokkeer toevoegen aan een opslaglocatie die al voorraad van een andere klant heeft.
    Transit-locaties (QC Hold, Inspection, etc.) worden overgeslagen.
    """
    loc_type = frappe.db.get_value("Storage Location", storage_location, "location_type") or ""
    if loc_type in _TRANSIT_LOCATION_TYPES:
        return  # Transit zones hoeven niet gesegregeerd te zijn

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
                    "Locatie {0} bevat al voorraad van {1}. "
                    "Kies een andere locatie voor {2}."
                ).format(
                    storage_location,
                    ("klant " + existing_customer) if existing_customer else "eigen voorraad",
                    ("klant " + customer) if customer else "eigen voorraad",
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

    customer = _get_customer_for_batch(batch_no)
    _validate_customer_on_location(storage_location, customer)

    existing = frappe.db.get_value(
        "Batch Location Stock",
        {
            "item_code": item_code,
            "batch_no": batch_no,
            "warehouse": warehouse,
            "storage_location": storage_location,
        },
        ["name", "qty"],
        as_dict=True,
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

    existing = frappe.db.get_value(
        "Batch Location Stock",
        {
            "item_code": item_code,
            "batch_no": batch_no,
            "warehouse": warehouse,
            "storage_location": storage_location,
        },
        ["name", "qty", "customer"],
        as_dict=True,
    )

    if not existing:
        frappe.throw(
            _(
                "Geen Batch Location Stock gevonden voor Item {0}, Batch {1}, "
                "Warehouse {2}, Locatie {3}."
            ).format(item_code, batch_no, warehouse, storage_location)
        )

    new_qty = flt(existing.qty) - qty
    if new_qty < -0.001:
        frappe.throw(
            _(
                "Kan {0} niet aftrekken van locatie {1}: slechts {2} beschikbaar "
                "voor Item {3} Batch {4}."
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

    customer = _get_customer_for_batch(batch_no)
    _validate_customer_on_location(to_location, customer)

    src = frappe.db.get_value(
        "Batch Location Stock",
        {
            "item_code": item_code,
            "batch_no": batch_no,
            "warehouse": warehouse,
            "storage_location": from_location,
        },
        ["name", "qty"],
        as_dict=True,
    )
    if not src:
        frappe.throw(
            _("Geen voorraad op locatie {0} voor Item {1} Batch {2}.").format(
                from_location, item_code, batch_no
            )
        )
    if flt(src.qty) < qty - 0.001:
        frappe.throw(
            _(
                "Onvoldoende voorraad op {0}: beschikbaar {1}, gevraagd {2} "
                "voor Item {3} Batch {4}."
            ).format(from_location, flt(src.qty, 3), flt(qty, 3), item_code, batch_no)
        )

    remaining = flt(src.qty) - qty

    dst = frappe.db.get_value(
        "Batch Location Stock",
        {
            "item_code": item_code,
            "batch_no": batch_no,
            "warehouse": warehouse,
            "storage_location": to_location,
        },
        ["name", "qty"],
        as_dict=True,
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
