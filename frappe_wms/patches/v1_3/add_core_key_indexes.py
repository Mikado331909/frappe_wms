"""
Add the missing composite indexes on the WMS core tables.

1. Batch Location Stock gets a UNIQUE index on the core key
   (item_code, batch_no, warehouse, storage_location). Before adding it,
   any duplicate rows (possible via manual creation, since the duplicate
   check lived only in Document.validate) are merged: quantities are summed
   into the oldest row and the newer duplicates are deleted.

2. Batch Location Movement gets a composite index on
   (reference_doctype, reference_name), used by the replay-based cancel
   logic, and posting_date for period reports. (from_location, to_location
   and reference_name single-column indexes come from the DocType JSON.)
"""

import frappe
from frappe.utils import flt

BLS_TABLE = "tabBatch Location Stock"
BLM_TABLE = "tabBatch Location Movement"
UNIQUE_INDEX = "uniq_item_batch_wh_location"


def execute():
    _merge_duplicate_bls_rows()
    _add_unique_index()
    _add_movement_indexes()


def _merge_duplicate_bls_rows():
    duplicates = frappe.db.sql(
        f"""
        SELECT item_code, batch_no, warehouse, storage_location,
               COUNT(*) AS row_count
        FROM `{BLS_TABLE}`
        GROUP BY item_code, batch_no, warehouse, storage_location
        HAVING COUNT(*) > 1
        """,
        as_dict=True,
    )

    for dup in duplicates:
        rows = frappe.db.sql(
            f"""
            SELECT name, qty FROM `{BLS_TABLE}`
            WHERE item_code = %(item_code)s
              AND batch_no = %(batch_no)s
              AND warehouse = %(warehouse)s
              AND storage_location = %(storage_location)s
            ORDER BY creation ASC
            FOR UPDATE
            """,
            dup,
            as_dict=True,
        )
        if len(rows) < 2:
            continue

        keeper = rows[0]
        total = sum(flt(r.qty) for r in rows)
        frappe.db.set_value(
            "Batch Location Stock", keeper.name, "qty", total,
            update_modified=False,
        )
        for extra in rows[1:]:
            frappe.delete_doc(
                "Batch Location Stock", extra.name,
                force=True, ignore_permissions=True,
            )


def _add_unique_index():
    existing = frappe.db.sql(
        f"SHOW INDEX FROM `{BLS_TABLE}` WHERE Key_name = %s", UNIQUE_INDEX
    )
    if existing:
        return
    frappe.db.sql_ddl(
        f"""
        ALTER TABLE `{BLS_TABLE}`
        ADD UNIQUE INDEX `{UNIQUE_INDEX}`
        (item_code, batch_no, warehouse, storage_location)
        """
    )


def _add_movement_indexes():
    if not frappe.db.sql(
        f"SHOW INDEX FROM `{BLM_TABLE}` WHERE Key_name = %s", "idx_reference"
    ):
        frappe.db.sql_ddl(
            f"""
            ALTER TABLE `{BLM_TABLE}`
            ADD INDEX `idx_reference` (reference_doctype, reference_name)
            """
        )
    if not frappe.db.sql(
        f"SHOW INDEX FROM `{BLM_TABLE}` WHERE Key_name = %s", "idx_posting_date"
    ):
        frappe.db.sql_ddl(
            f"""
            ALTER TABLE `{BLM_TABLE}`
            ADD INDEX `idx_posting_date` (posting_date)
            """
        )
