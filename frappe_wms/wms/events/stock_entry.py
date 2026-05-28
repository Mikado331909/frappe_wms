import frappe
from frappe_wms.wms.events.utils import (
    iter_batch_entries,
    get_receiving_location,
    get_picking_staging_location,
    add_location_qty,
    deduct_location_qty,
)


def on_submit(doc, method=None):
    for item in doc.items:
        _process_source(doc, item)
        _process_target(doc, item)


def _process_source(doc, item):
    s_warehouse = item.s_warehouse
    if not s_warehouse:
        return
    staging_loc = get_picking_staging_location(s_warehouse, raise_if_missing=False)
    if not staging_loc:
        return
    for batch_no, qty in iter_batch_entries(item):
        staging_qty = (
            frappe.db.get_value(
                "Batch Location Stock",
                {
                    "item_code": item.item_code,
                    "batch_no": batch_no,
                    "warehouse": s_warehouse,
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
            warehouse=s_warehouse,
            storage_location=staging_loc,
            qty=deduct_qty,
            ref_doctype="Stock Entry",
            ref_name=doc.name,
        )


def _process_target(doc, item):
    t_warehouse = item.t_warehouse
    if not t_warehouse:
        return
    receiving_loc = get_receiving_location(t_warehouse, raise_if_missing=False)
    if not receiving_loc:
        return
    for batch_no, qty in iter_batch_entries(item):
        add_location_qty(
            item_code=item.item_code,
            batch_no=batch_no,
            warehouse=t_warehouse,
            storage_location=receiving_loc,
            qty=qty,
            uom=item.uom,
            ref_doctype="Stock Entry",
            ref_name=doc.name,
        )
