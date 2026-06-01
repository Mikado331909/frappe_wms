"""
Shared helpers for all WMS event handlers.

Rules
-----
* Every qty change to Batch Location Stock must produce a Batch Location Movement row.
* These functions are the only permitted writers of Batch Location Stock rows —
  manual UI saves go through BatchLocationStock.validate() instead.
* `raise_if_missing=False` lets callers skip silently for non-WMS warehouses.

ERPNext v16 note
----------------
v16 tracks batches via "Serial and Batch Bundle" (child: "Serial and Batch Entry")
instead of a direct batch_no field on transaction items.  Use
`iter_batch_entries(item)` to transparently handle both old and new style.
"""

import frappe
from frappe import _
from frappe.utils import nowdate, nowtime, flt


# ---------------------------------------------------------------------------
# ERPNext v16 Serial and Batch Bundle helper
# ---------------------------------------------------------------------------


def iter_batch_entries(item):
    """
    Yield (batch_no, qty) pairs for a transaction item row.

    Handles both:
      - ERPNext <=15 style: item.batch_no + item.qty
      - ERPNext v16 style:  item.serial_and_batch_bundle -> Serial and Batch Entry rows

    ERPNext v16 creates the Serial and Batch Bundle during its own on_submit,
    so the in-memory item object may not have it yet — we re-read from DB.
    """
    # In-memory value (may be None if bundle was just created during submit)
    bundle = getattr(item, "serial_and_batch_bundle", None)

    # Re-read from DB if not set in memory
    if not bundle and getattr(item, "name", None) and getattr(item, "doctype", None):
        bundle = frappe.db.get_value(
            item.doctype, item.name, "serial_and_batch_bundle"
        )

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


def _get_customer_for_batch(batch_no):
    """Resolve the customer linked to a batch."""
    if not batch_no:
        return None
    return frappe.db.get_value("Batch", batch_no, "customer") or None


def _validate_customer_on_location(storage_location, customer):
    """
    Blokkeer toevoegen aan een locatie die al voorraad van een andere eigenaar heeft.
    Regels:
      - klant X + klant Y        → geblokkeerd
      - klant X + eigen voorraad → geblokkeerd
      - eigen voorraad + klant X → geblokkeerd
      - klant X + klant X        → toegestaan
      - eigen voorraad + eigen   → toegestaan
    Zero-qty records worden genegeerd zodat lege locaties hergebruikt kunnen worden.
    """
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
                    existing_customer or "eigen voorraad",
                    customer or "eigen voorraad",
                )
            )


def add_location_qty(
    item_code, batch_no, warehouse, storage_location, qty, uom, ref_doctype, ref_name
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
                "customer": customer,
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
        customer=customer,
    )


def deduct_location_qty(
    item_code, batch_no, warehouse, storage_location, qty, ref_doctype, ref_name
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

    # Record movement BEFORE deleting so the Dynamic Link validation passes
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
    )

    final_qty = max(new_qty, 0.0)
    frappe.db.set_value("Batch Location Stock", existing.name, "qty", final_qty)


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
            _("No stock in location {0} for Item {1} Batch {2}.").format(
                from_location, item_code, batch_no
            )
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
        new_doc = frappe.get_doc(
            {
                "doctype": "Batch Location Stock",
                "item_code": item_code,
                "batch_no": batch_no,
                "warehouse": warehouse,
                "storage_location": to_location,
                "qty": qty,
                "uom": uom,
                "customer": customer,
            }
        )
        new_doc.flags.ignore_validate = True
        new_doc.insert(ignore_permissions=True)

    # Record movement BEFORE deleting source so Dynamic Link validation passes
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
    )

    frappe.db.set_value("Batch Location Stock", src.name, "qty", max(remaining, 0.0))


# ---------------------------------------------------------------------------
# Internal audit writer
# ---------------------------------------------------------------------------


def _record_movement(
    item_code, batch_no, warehouse, from_location, to_location, qty, ref_doctype, ref_name,
    customer=None,
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
            "customer": customer,
        }
    ).insert(ignore_permissions=True)
