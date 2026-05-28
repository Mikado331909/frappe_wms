"""
Delivery Note submit hook.

Consumes batch qty from the Picking Staging location of the source warehouse.
Silently skips warehouses that have no Picking Staging location configured.
"""

import frappe
from frappe_wms.wms.events.utils import get_picking_staging_location, deduct_location_qty


def on_submit(doc, method=None):
    for item in doc.items:
        if not item.batch_no:
            continue
        warehouse = item.warehouse or doc.set_warehouse
        if not warehouse:
            continue
        staging_loc = get_picking_staging_location(warehouse, raise_if_missing=False)
        if not staging_loc:
            continue
        staging_qty = (
            frappe.db.get_value(
                "Batch Location Stock",
                {
                    "item_code": item.item_code,
                    "batch_no": item.batch_no,
                    "warehouse": warehouse,
                    "storage_location": staging_loc,
                },
                "qty",
            )
            or 0.0
        )
        if frappe.utils.flt(staging_qty) < 0.001:
            continue
        deduct_qty = min(frappe.utils.flt(item.qty), frappe.utils.flt(staging_qty))
        deduct_location_qty(
            item_code=item.item_code,
            batch_no=item.batch_no,
            warehouse=warehouse,
            storage_location=staging_loc,
            qty=deduct_qty,
            ref_doctype="Delivery Note",
            ref_name=doc.name,
        )
