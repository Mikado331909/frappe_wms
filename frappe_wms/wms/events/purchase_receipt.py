import frappe
from frappe_wms.wms.events.utils import (
    get_receiving_location,
    add_location_qty,
    deduct_location_qty,
)


def on_submit(doc, method=None):
    if not frappe.db.get_single_value("WMS Settings", "auto_create_on_receipt"):
        return
    for item in doc.items:
        if not item.batch_no:
            continue
        warehouse = item.t_warehouse or item.warehouse or doc.set_warehouse
        if not warehouse:
            continue
        receiving_loc = get_receiving_location(warehouse, raise_if_missing=False)
        if not receiving_loc:
            continue
        add_location_qty(
            item_code=item.item_code,
            batch_no=item.batch_no,
            warehouse=warehouse,
            storage_location=receiving_loc,
            qty=item.qty,
            uom=item.uom,
            ref_doctype="Purchase Receipt",
            ref_name=doc.name,
        )


def on_cancel(doc, method=None):
    if not frappe.db.get_single_value("WMS Settings", "auto_create_on_receipt"):
        return
    for item in doc.items:
        if not item.batch_no:
            continue
        warehouse = item.t_warehouse or item.warehouse or doc.set_warehouse
        if not warehouse:
            continue
        receiving_loc = get_receiving_location(warehouse, raise_if_missing=False)
        if not receiving_loc:
            continue
        deduct_location_qty(
            item_code=item.item_code,
            batch_no=item.batch_no,
            warehouse=warehouse,
            storage_location=receiving_loc,
            qty=item.qty,
            ref_doctype="Purchase Receipt Cancel",
            ref_name=doc.name,
        )
