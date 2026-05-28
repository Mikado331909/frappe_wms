"""
Stock Entry submit hook.

Intent:
  - If the source warehouse has a Picking Staging location AND the batch
    has qty there, consume it (goods were pre-picked before the transfer).
  - If the target warehouse has a Receiving location, place incoming qty
    there (e.g. internal transfer receives into Receiving before putaway).

Both actions are best-effort: warehouses without WMS locations are silently
skipped so the hook never blocks an ERPNext stock transaction.
"""

import frappe
from frappe_wms.wms.events.utils import (
    get_receiving_location,
    get_picking_staging_location,
    add_location_qty,
    deduct_location_qty,
)


def on_submit(doc, method=None):
    for item in doc.items:
        if not item.batch_no:
            continue
        _process_source(doc, item)
        _process_target(doc, item)


def _process_source(doc, item):
    s_warehouse = item.s_warehouse
    if not s_warehouse:
        return
    staging_loc = get_picking_staging_location(s_warehouse, raise_if_missing=False)
    if not staging_loc:
        return
    # Only deduct if staging actually has qty for this batch — skip silently otherwise
    staging_qty = (
        frappe.db.get_value(
            "Batch Location Stock",
            {
                "item_code": item.item_code,
                "batch_no": item.batch_no,
                "warehouse": s_warehouse,
                "storage_location": staging_loc,
            },
            "qty",
        )
        or 0.0
    )
    if frappe.utils.flt(staging_qty) < 0.001:
        return
    deduct_qty = min(frappe.utils.flt(item.qty), frappe.utils.flt(staging_qty))
    deduct_location_qty(
        item_code=item.item_code,
        batch_no=item.batch_no,
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
    add_location_qty(
        item_code=item.item_code,
        batch_no=item.batch_no,
        warehouse=t_warehouse,
        storage_location=receiving_loc,
        qty=item.qty,
        uom=item.uom,
        ref_doctype="Stock Entry",
        ref_name=doc.name,
    )
