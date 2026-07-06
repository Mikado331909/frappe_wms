import frappe
from frappe_wms.wms.events.utils import (
    iter_batch_entries,
    get_picking_staging_location,
    deduct_location_qty,
)


def on_submit(doc, method=None):
    for item in doc.items:
        warehouse = item.warehouse or doc.set_warehouse
        if not warehouse:
            continue
        staging_loc = get_picking_staging_location(warehouse, raise_if_missing=False)
        if not staging_loc:
            continue
        for batch_no, qty in iter_batch_entries(item):
            staging_qty = (
                frappe.db.get_value(
                    "Batch Location Stock",
                    {
                        "item_code": item.item_code,
                        "batch_no": batch_no,
                        "warehouse": warehouse,
                        "storage_location": staging_loc,
                    },
                    "qty",
                )
                or 0.0
            )
            if frappe.utils.flt(staging_qty) < 0.001:
                continue
            deduct_qty = min(qty, frappe.utils.flt(staging_qty))
            deduct_location_qty(
                item_code=item.item_code,
                batch_no=batch_no,
                warehouse=warehouse,
                storage_location=staging_loc,
                qty=deduct_qty,
                ref_doctype="Delivery Note",
                ref_name=doc.name,
                movement_type="Pick",
            )


def on_cancel(doc, method=None):
    """Restore WMS staging stock deducted at submit (exact replay)."""
    from frappe_wms.wms.events.utils import reverse_reference_movements

    reverse_reference_movements("Delivery Note", doc.name)
