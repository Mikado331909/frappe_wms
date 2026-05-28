"""
Shared helpers for all WMS event handlers.

Rules
-----
* Every qty change to Batch Location Stock must produce a Batch Location Movement row.
* These functions are the only permitted writers of Batch Location Stock rows —
  manual UI saves go through BatchLocationStock.validate() instead.
* `raise_if_missing=False` lets callers skip silently for non-WMS warehouses.
"""

import frappe
from frappe import _
from frappe.utils import nowdate, nowtime, flt


# ---------------------------------------------------------------------------
# Location lookup
# ---------------------------------------------------------------------------


def get_receiving_location(warehouse, raise_if_missing=True):
    loc = frappe.db.get_value(
        "Storage Location",
        {"warehouse": warehouse, "location_type": "Receiving", "is_active": 1},
        "name",
        order_by="pick_sequence asc",
    )
    if not loc and raise_if_missing:
        frappe.throw(
            _("No active Receiving location found for warehouse {0}.").format(warehouse)
        )
    return loc


def get_picking_staging_location(warehouse, raise_if_missing=True):
    loc = frappe.db.get_value(
        "Storage Location",
        {"warehouse": warehouse, "location_type": "Picking Staging", "is_active": 1},
        "name",
        order_by="pick_sequence asc",
    )
    if not loc and raise_if_missing:
        frappe.throw(
            _(
                "No active Picking Staging location found for warehouse {0}."
            ).format(warehouse)
        )
    return loc


# ---------------------------------------------------------------------------
# Qty mutations
# ---------------------------------------------------------------------------


def add_location_qty(
    item_code, batch_no, warehouse, storage_location, qty, uom, ref_doctype, ref_name
):
    """Create or increment a Batch Location Stock row and record the movement."""
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
        ["name", "qty"],
        as_dict=True,
    )

    if existing:
        new_qty = flt(existing.qty) + qty
        frappe.db.set_value("Batch Location Stock", existing.name, "qty", new_qty)
    else:
        if not uom:
            uom = frappe.db.get_value("Item", item_code, "stock_uom")
        doc = frappe.get_doc(
            {
                "doctype": "Batch Location Stock",
                "item_code": item_code,
                "batch_no": batch_no,
                "warehouse": warehouse,
                "storage_location": storage_location,
                "qty": qty,
                "uom": uom,
            }
        )
        # Skip cross-validate on first insert (ERPNext stock may not yet be posted)
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
    )


def deduct_location_qty(
    item_code, batch_no, warehouse, storage_location, qty, ref_doctype, ref_name
):
    """Reduce a Batch Location Stock row and record the movement.

    Raises ValidationError if the row does not exist or has insufficient qty.
    """
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
        ["name", "qty"],
        as_dict=True,
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
                flt(qty, 3),
                storage_location,
                flt(existing.qty, 3),
                item_code,
                batch_no,
            )
        )

    frappe.db.set_value(
        "Batch Location Stock", existing.name, "qty", max(new_qty, 0.0)
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
    )


def move_location_qty(
    item_code,
    batch_no,
    warehouse,
    from_location,
    to_location,
    qty,
    ref_doctype,
    ref_name,
):
    """Atomically move qty between two locations in the same warehouse."""
    qty = flt(qty)
    if qty <= 0:
        return

    # --- source ---
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
            _(
                "No stock in location {0} for Item {1} Batch {2}."
            ).format(from_location, item_code, batch_no)
        )
    if flt(src.qty) < qty - 0.001:
        frappe.throw(
            _(
                "Insufficient qty in {0}: available {1}, requested {2} "
                "for Item {3} Batch {4}."
            ).format(
                from_location,
                flt(src.qty, 3),
                flt(qty, 3),
                item_code,
                batch_no,
            )
        )
    frappe.db.set_value(
        "Batch Location Stock", src.name, "qty", flt(src.qty) - qty
    )

    # --- destination ---
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
        frappe.db.set_value(
            "Batch Location Stock", dst.name, "qty", flt(dst.qty) + qty
        )
    else:
        uom = frappe.db.get_value("Item", item_code, "stock_uom")
        new_doc = frappe.get_doc(
            {
                "doctype": "Batch Location Stock",
                "item_code": item_code,
                "batch_no": batch_no,
                "warehouse": warehouse,
                "storage_location": to_location,
                "qty": qty,
                "uom": uom,
            }
        )
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
    )


# ---------------------------------------------------------------------------
# Internal audit writer
# ---------------------------------------------------------------------------


def _record_movement(
    item_code, batch_no, warehouse, from_location, to_location, qty, ref_doctype, ref_name
):
    frappe.get_doc(
        {
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
        }
    ).insert(ignore_permissions=True)
