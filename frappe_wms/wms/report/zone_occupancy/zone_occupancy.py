"""
Zone Occupancy rapport — bezettingsgraad per zone.
Toont voor elke zone: huidige voorraad, capaciteit en bezetting %.
"""
import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    return _columns(), _get_data(filters)


def _columns():
    return [
        {"label": "Zone", "fieldname": "zone", "fieldtype": "Link", "options": "WMS Zone", "width": 130},
        {"label": "Zone Naam", "fieldname": "zone_name", "fieldtype": "Data", "width": 160},
        {"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 150},
        {"label": "Zone Type", "fieldname": "zone_type", "fieldtype": "Data", "width": 140},
        {"label": "Klant", "fieldname": "dedicated_customer", "fieldtype": "Link", "options": "Customer", "width": 130},
        {"label": "Actieve Locaties", "fieldname": "active_locations", "fieldtype": "Int", "width": 110},
        {"label": "Bezette Locaties", "fieldname": "occupied_locations", "fieldtype": "Int", "width": 110},
        {"label": "Totale Capaciteit", "fieldname": "total_capacity", "fieldtype": "Float", "width": 120},
        {"label": "Huidige Voorraad", "fieldname": "current_stock", "fieldtype": "Float", "width": 120},
        {"label": "Bezetting %", "fieldname": "occupancy_pct", "fieldtype": "Percent", "width": 100},
    ]


def _get_data(filters):
    conditions = []
    values = {}

    if filters.get("warehouse"):
        conditions.append("z.warehouse = %(warehouse)s")
        values["warehouse"] = filters["warehouse"]
    if filters.get("zone_type"):
        conditions.append("z.zone_type = %(zone_type)s")
        values["zone_type"] = filters["zone_type"]

    where = "WHERE z.is_active = 1"
    if conditions:
        where += " AND " + " AND ".join(conditions)

    rows = frappe.db.sql(f"""
        SELECT
            z.name AS zone,
            z.zone_name,
            z.warehouse,
            z.zone_type,
            z.dedicated_customer,
            COUNT(DISTINCT sl.name) AS active_locations,
            COUNT(DISTINCT CASE WHEN bls.qty > 0 THEN sl.name END) AS occupied_locations,
            COALESCE(SUM(sl.max_qty), 0) AS total_capacity,
            COALESCE(SUM(bls.qty), 0) AS current_stock
        FROM `tabWMS Zone` z
        LEFT JOIN `tabStorage Location` sl ON sl.zone = z.name AND sl.is_active = 1
        LEFT JOIN `tabBatch Location Stock` bls ON bls.storage_location = sl.name
        {where}
        GROUP BY z.name
        ORDER BY z.warehouse, z.zone_name
    """, values, as_dict=True)

    data = []
    for row in rows:
        cap = flt(row.total_capacity)
        stock = flt(row.current_stock)
        pct = round(stock / cap * 100, 1) if cap > 0 else 0
        data.append({
            "zone": row.zone,
            "zone_name": row.zone_name,
            "warehouse": row.warehouse,
            "zone_type": row.zone_type,
            "dedicated_customer": row.dedicated_customer,
            "active_locations": row.active_locations or 0,
            "occupied_locations": row.occupied_locations or 0,
            "total_capacity": flt(cap, 3),
            "current_stock": flt(stock, 3),
            "occupancy_pct": pct,
        })
    return data
