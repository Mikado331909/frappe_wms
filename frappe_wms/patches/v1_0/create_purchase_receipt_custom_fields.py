"""
Create WMS custom fields on Purchase Receipt Item.

These fields allow per-line configuration on a Purchase Receipt:
  - wms_customer       : which customer owns this receipt line
  - wms_require_qc     : send to QC Hold instead of RECV
  - wms_cross_dock     : send to Cross-dock Staging instead of RECV
  - wms_cross_dock_so  : linked Sales Order for the cross-dock
"""
import frappe


_FIELDS = [
    {
        "dt": "Batch",
        "fieldname": "customer",
        "fieldtype": "Link",
        "options": "Customer",
        "label": "Customer (WMS)",
        "insert_after": "item",
        "description": "Customer that owns this batch for WMS segregation.",
    },
    {
        "dt": "Purchase Receipt Item",
        "fieldname": "wms_customer",
        "fieldtype": "Link",
        "options": "Customer",
        "label": "Customer (WMS)",
        "insert_after": "item_name",
        "in_list_view": 0,
        "description": (
            "Customer for whom this line is received. "
            "Copied to WMS location stock."
        ),
    },
    {
        "dt": "Purchase Receipt Item",
        "fieldname": "wms_require_qc",
        "fieldtype": "Check",
        "label": "QC Required",
        "insert_after": "wms_customer",
        "default": "0",
        "description": (
            "If checked: the item goes to a QC Hold location "
            "and a WMS QC Check is created."
        ),
    },
    {
        "dt": "Purchase Receipt Item",
        "fieldname": "wms_cross_dock",
        "fieldtype": "Check",
        "label": "Cross-dock",
        "insert_after": "wms_require_qc",
        "default": "0",
        "description": (
            "If checked: the item goes to a Cross-dock Staging location "
            "for direct flow-through."
        ),
    },
    {
        "dt": "Purchase Receipt Item",
        "fieldname": "wms_cross_dock_so",
        "fieldtype": "Link",
        "options": "Sales Order",
        "label": "Cross-dock Sales Order",
        "insert_after": "wms_cross_dock",
        "depends_on": "eval:doc.wms_cross_dock == 1",
        "description": "Linked Sales Order for this cross-dock shipment.",
    },
]


def execute():
    for field in _FIELDS:
        if frappe.db.exists("Custom Field", {"dt": field["dt"], "fieldname": field["fieldname"]}):
            continue

        cf = frappe.get_doc({"doctype": "Custom Field", **field})
        cf.insert(ignore_permissions=True)

    frappe.db.commit()
    frappe.clear_cache()
