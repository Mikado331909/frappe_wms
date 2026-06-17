"""
Customer Stock Overview - stock per customer, zone and item.
"""
import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    return _columns(), _get_data(filters)


def _columns():
    return [
        {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
        {"label": _("Zone"), "fieldname": "zone", "fieldtype": "Link", "options": "WMS Zone", "width": 120},
        {"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 140},
        {"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
        {"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
        {"label": _("Batch"), "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 120},
        {"label": _("Location"), "fieldname": "storage_location", "fieldtype": "Link", "options": "Storage Location", "width": 120},
        {"label": _("Quantity"), "fieldname": "qty", "fieldtype": "Float", "width": 100},
        {"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 70},
    ]


def _get_data(filters):
    conditions = ["bls.qty > 0"]
    values = {}

    if filters.get("customer"):
        conditions.append("bls.customer = %(customer)s")
        values["customer"] = filters["customer"]
    if filters.get("warehouse"):
        conditions.append("bls.warehouse = %(warehouse)s")
        values["warehouse"] = filters["warehouse"]
    if filters.get("zone"):
        conditions.append("bls.zone = %(zone)s")
        values["zone"] = filters["zone"]

    where = "WHERE " + " AND ".join(conditions)

    return frappe.db.sql(f"""
        SELECT
            COALESCE(bls.customer, '(Company Stock)') AS customer,
            bls.zone,
            bls.warehouse,
            bls.item_code,
            i.item_name,
            bls.batch_no,
            bls.storage_location,
            bls.qty,
            bls.uom
        FROM `tabBatch Location Stock` bls
        LEFT JOIN `tabItem` i ON i.name = bls.item_code
        {where}
        ORDER BY bls.customer, bls.zone, bls.item_code, bls.storage_location
    """, values, as_dict=True)
