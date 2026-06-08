import frappe


def execute():
    """Add customer column to Batch Location Stock and Batch Location Movement,
    then backfill from the linked Batch record."""

    for table in ("tabBatch Location Stock", "tabBatch Location Movement"):
        # Use IF NOT EXISTS so the patch is safe to re-run
        try:
            frappe.db.sql(
                f"ALTER TABLE `{table}` ADD COLUMN IF NOT EXISTS `customer` VARCHAR(140) DEFAULT NULL"
            )
        except Exception:
            # Column may already exist on some DB versions that don't support IF NOT EXISTS
            pass

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
