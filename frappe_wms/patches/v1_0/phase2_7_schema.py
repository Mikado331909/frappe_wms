"""
Fasen 2-7 schema patch:
- Voegt nieuwe custom fields toe aan Purchase Receipt Item
- Voegt movement_type toe aan bestaande BLM records (backfill)
"""
import frappe


def _column_exists(table, column):
    return bool(frappe.db.sql(f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,)))


def _add_col(table, column, col_type):
    if _column_exists(table, column):
        return

    try:
        frappe.db.sql(
            f"ALTER TABLE `{table}` ADD COLUMN IF NOT EXISTS `{column}` {col_type}"
        )
    except Exception:
        pass

    if not _column_exists(table, column):
        frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {col_type}")


def execute():
    # ------------------------------------------------------------------
    # Custom fields op Purchase Receipt Item (naast wms_customer)
    # ------------------------------------------------------------------
    custom_fields = [
        {
            "dt": "Purchase Receipt Item",
            "fieldname": "wms_require_qc",
            "fieldtype": "Check",
            "label": "QC Vereist",
            "insert_after": "wms_customer",
            "default": "0",
        },
        {
            "dt": "Purchase Receipt Item",
            "fieldname": "wms_cross_dock",
            "fieldtype": "Check",
            "label": "Cross-dock",
            "insert_after": "wms_require_qc",
            "default": "0",
        },
        {
            "dt": "Purchase Receipt Item",
            "fieldname": "wms_cross_dock_so",
            "fieldtype": "Link",
            "options": "Sales Order",
            "label": "Cross-dock Sales Order",
            "insert_after": "wms_cross_dock",
            "depends_on": "eval:doc.wms_cross_dock == 1",
        },
    ]

    for cf in custom_fields:
        if not frappe.db.exists("Custom Field", {"dt": cf["dt"], "fieldname": cf["fieldname"]}):
            frappe.get_doc({"doctype": "Custom Field", **cf}).insert(ignore_permissions=True)

    # ------------------------------------------------------------------
    # Backfill movement_type voor bestaande Batch Location Movement records
    # ------------------------------------------------------------------
    _add_col("tabBatch Location Movement", "movement_type", "varchar(50) DEFAULT NULL")

    # Inbound (geen from_location)
    frappe.db.sql("""
        UPDATE `tabBatch Location Movement`
        SET movement_type = 'Inbound'
        WHERE from_location IS NULL
          AND to_location IS NOT NULL
          AND (movement_type IS NULL OR movement_type = '')
    """)

    # Pick (reference = Location Pick)
    frappe.db.sql("""
        UPDATE `tabBatch Location Movement`
        SET movement_type = 'Pick'
        WHERE reference_doctype IN ('Location Pick', 'Delivery Note')
          AND (movement_type IS NULL OR movement_type = '')
    """)

    # Production
    frappe.db.sql("""
        UPDATE `tabBatch Location Movement`
        SET movement_type = 'Production'
        WHERE reference_doctype = 'Stock Entry'
          AND (movement_type IS NULL OR movement_type = '')
    """)

    frappe.db.commit()
