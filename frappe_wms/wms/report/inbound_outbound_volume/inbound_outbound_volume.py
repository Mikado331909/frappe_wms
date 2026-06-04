"""
Inbound / Outbound Volume rapport — bewegingsvolume per dag per bewegingstype.
"""
import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    return _columns(), _get_data(filters)


def _columns():
    return [
        {"label": "Datum", "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 140},
        {"label": "Bewegingstype", "fieldname": "movement_type", "fieldtype": "Data", "width": 140},
        {"label": "Klant", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 130},
        {"label": "Aantal Bewegingen", "fieldname": "movement_count", "fieldtype": "Int", "width": 120},
        {"label": "Totaal Hoeveelheid", "fieldname": "total_qty", "fieldtype": "Float", "width": 120},
    ]


def _get_data(filters):
    conditions = []
    values = {}

    if filters.get("from_date"):
        conditions.append("blm.posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("blm.posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]
    if filters.get("warehouse"):
        conditions.append("blm.warehouse = %(warehouse)s")
        values["warehouse"] = filters["warehouse"]
    if filters.get("movement_type"):
        conditions.append("blm.movement_type = %(movement_type)s")
        values["movement_type"] = filters["movement_type"]

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    return frappe.db.sql(f"""
        SELECT
            blm.posting_date,
            blm.warehouse,
            COALESCE(blm.movement_type, 'Onbekend') AS movement_type,
            blm.customer,
            COUNT(*) AS movement_count,
            SUM(blm.qty) AS total_qty
        FROM `tabBatch Location Movement` blm
        {where}
        GROUP BY blm.posting_date, blm.warehouse, blm.movement_type, blm.customer
        ORDER BY blm.posting_date DESC, blm.warehouse
    """, values, as_dict=True)
