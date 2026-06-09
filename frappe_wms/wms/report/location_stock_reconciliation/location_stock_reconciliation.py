"""
ERPNext-vs-Location-Stock Reconciliation report.

For every Item + Batch + Warehouse combination that has Batch Location Stock
rows, shows:
  - Total location qty  (sum of all storage location rows)
  - ERPNext actual qty  (sum of non-cancelled SLE actual_qty)
  - Difference          (ERPNext qty − location qty)

A non-zero Difference indicates that location stock is out of sync with
ERPNext and needs manual investigation or correction.
"""

import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    columns = _columns()
    data = _get_data(filters)
    return columns, data


def _columns():
    return [
        {
            "label": "Item Code",
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 150,
        },
        {
            "label": "Item Name",
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": "Batch No",
            "fieldname": "batch_no",
            "fieldtype": "Link",
            "options": "Batch",
            "width": 130,
        },
        {
            "label": "Warehouse",
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 160,
        },
        {
            "label": "ERPNext Qty",
            "fieldname": "erpnext_qty",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": "Location Qty",
            "fieldname": "location_qty",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": "Difference",
            "fieldname": "difference",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": "Location Breakdown",
            "fieldname": "location_breakdown",
            "fieldtype": "Data",
            "width": 300,
        },
    ]


def _get_data(filters):
    conditions = []
    values = {}

    if filters.get("warehouse"):
        conditions.append("bls.warehouse = %(warehouse)s")
        values["warehouse"] = filters["warehouse"]
    if filters.get("item_code"):
        conditions.append("bls.item_code = %(item_code)s")
        values["item_code"] = filters["item_code"]
    if filters.get("batch_no"):
        conditions.append("bls.batch_no = %(batch_no)s")
        values["batch_no"] = filters["batch_no"]

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Aggregate location stock per item+batch+warehouse
    location_rows = frappe.db.sql(
        f"""
        SELECT
            bls.item_code,
            i.item_name,
            bls.batch_no,
            bls.warehouse,
            SUM(bls.qty) AS location_qty,
            GROUP_CONCAT(
                CONCAT(bls.storage_location, ': ', bls.qty)
                ORDER BY bls.storage_location
                SEPARATOR ' | '
            ) AS location_breakdown
        FROM `tabBatch Location Stock` bls
        LEFT JOIN `tabItem` i ON i.name = bls.item_code
        {where}
        GROUP BY bls.item_code, bls.batch_no, bls.warehouse
        ORDER BY bls.item_code, bls.batch_no, bls.warehouse
        """,
        values,
        as_dict=True,
    )

    data = []
    for row in location_rows:
        erpnext_qty = _get_sle_qty(row.item_code, row.batch_no, row.warehouse)
        loc_qty = flt(row.location_qty)
        diff = flt(erpnext_qty) - loc_qty

        only_discrepancies = filters.get("only_discrepancies")
        if only_discrepancies and abs(diff) < 0.001:
            continue

        data.append(
            {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "batch_no": row.batch_no,
                "warehouse": row.warehouse,
                "erpnext_qty": flt(erpnext_qty, 3),
                "location_qty": flt(loc_qty, 3),
                "difference": flt(diff, 3),
                "location_breakdown": row.location_breakdown,
            }
        )

    return data


def _get_sle_qty(item_code, batch_no, warehouse):
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM(sle.actual_qty), 0)
        FROM `tabStock Ledger Entry` sle
        WHERE sle.item_code = %(item_code)s
          AND sle.warehouse = %(warehouse)s
          AND sle.is_cancelled = 0
          AND (
            sle.batch_no = %(batch_no)s
            OR EXISTS (
                SELECT 1
                FROM `tabSerial and Batch Entry` sbe
                WHERE sbe.parent = sle.serial_and_batch_bundle
                  AND sbe.batch_no = %(batch_no)s
            )
          )
        """,
        {"item_code": item_code, "batch_no": batch_no, "warehouse": warehouse},
    )
    return flt(result[0][0]) if result else 0.0
