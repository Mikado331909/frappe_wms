import frappe


def _column_exists(table, column):
    return bool(frappe.db.sql(f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,)))


def _add_col(table, column, col_type):
    try:
        frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN IF NOT EXISTS `{column}` {col_type}")
    except Exception:
        # Older MariaDB versions may not support IF NOT EXISTS.
        if not _column_exists(table, column):
            frappe.db.sql(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {col_type}")


def _ensure_batch_customer_field():
    """Ensure Batch has the customer field used by the WMS ownership logic."""
    if not frappe.db.exists("Custom Field", {"dt": "Batch", "fieldname": "customer"}):
        try:
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Batch",
                "fieldname": "customer",
                "fieldtype": "Link",
                "options": "Customer",
                "label": "Customer (WMS)",
                "insert_after": "item",
                "description": "Customer that owns this batch for WMS segregation.",
            }).insert(ignore_permissions=True)
            frappe.clear_cache(doctype="Batch")
        except Exception:
            # The SQL column is enough for this patch and the event handlers.
            # If the Custom Field insert failed because of schema timing, keep
            # migration moving and let fixtures/custom-field patches retry later.
            pass

    if not _column_exists("tabBatch", "customer"):
        _add_col("tabBatch", "customer", "varchar(140) DEFAULT NULL")


def execute():
    """Add customer column to Batch Location Stock and Batch Location Movement,
    then backfill from the linked Batch record."""

    _ensure_batch_customer_field()

    for table in ("tabBatch Location Stock", "tabBatch Location Movement"):
        _add_col(table, "customer", "varchar(140) DEFAULT NULL")

    frappe.db.sql("""
        UPDATE `tabBatch Location Stock` bls
        INNER JOIN `tabBatch` b ON b.name = bls.batch_no
        SET bls.customer = b.customer
        WHERE b.customer IS NOT NULL AND b.customer != ''
          AND (bls.customer IS NULL OR bls.customer = '')
    """)

    frappe.db.sql("""
        UPDATE `tabBatch Location Movement` blm
        INNER JOIN `tabBatch` b ON b.name = blm.batch_no
        SET blm.customer = b.customer
        WHERE b.customer IS NOT NULL AND b.customer != ''
          AND (blm.customer IS NULL OR blm.customer = '')
    """)

    frappe.db.commit()
