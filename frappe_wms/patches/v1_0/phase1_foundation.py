"""
Phase 1 foundation patch:
- Add zone + max_qty to Storage Location
- Add zone to Batch Location Stock and backfill it
- Add movement_type to Batch Location Movement and backfill it
- Add pick_list to Location Pick Line and backfill it from Pick List Item
- Migrate Location Pick.pick_list to the Location Pick Source child table
"""
import frappe


def _column_exists(table, column):
    return bool(frappe.db.sql(f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,)))


def _table_exists(table):
    return bool(frappe.db.sql("SHOW TABLES LIKE %s", (table,)))


def _add_col(table, column, col_type):
    """Add column if it doesn't exist - safe to re-run."""
    if _column_exists(table, column):
        return

    try:
        frappe.db.sql_ddl(
            f"ALTER TABLE `{table}` ADD COLUMN IF NOT EXISTS `{column}` {col_type}"
        )
    except Exception:
        pass

    if not _column_exists(table, column):
        frappe.db.sql_ddl(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {col_type}")


def execute():
    # Storage Location: zone + max_qty
    _add_col("tabStorage Location", "zone", "varchar(140) DEFAULT NULL")
    _add_col("tabStorage Location", "max_qty", "decimal(21,9) DEFAULT 0")

    # Batch Location Stock: zone
    _add_col("tabBatch Location Stock", "zone", "varchar(140) DEFAULT NULL")

    # Batch Location Movement: movement_type
    _add_col("tabBatch Location Movement", "movement_type", "varchar(50) DEFAULT NULL")

    # Location Pick Line: pick_list
    _add_col("tabLocation Pick Line", "pick_list", "varchar(140) DEFAULT NULL")

    # Backfill zone from Storage Location.
    frappe.db.sql("""
        UPDATE `tabBatch Location Stock` bls
        INNER JOIN `tabStorage Location` sl ON sl.name = bls.storage_location
        SET bls.zone = sl.zone
        WHERE sl.zone IS NOT NULL AND sl.zone != ''
          AND (bls.zone IS NULL OR bls.zone = '')
    """)

    # Backfill existing inbound movements.
    frappe.db.sql("""
        UPDATE `tabBatch Location Movement`
        SET movement_type = 'Inbound'
        WHERE from_location IS NULL
          AND to_location IS NOT NULL
          AND (movement_type IS NULL OR movement_type = '')
    """)

    frappe.db.sql("""
        UPDATE `tabBatch Location Movement`
        SET movement_type = 'Pick'
        WHERE reference_doctype = 'Location Pick'
          AND (movement_type IS NULL OR movement_type = '')
    """)

    # Backfill from Pick List Item to parent Pick List.
    frappe.db.sql("""
        UPDATE `tabLocation Pick Line` lpl
        INNER JOIN `tabPick List Item` pli ON pli.name = lpl.pick_list_item
        SET lpl.pick_list = pli.parent
        WHERE (lpl.pick_list IS NULL OR lpl.pick_list = '')
          AND pli.parent IS NOT NULL
    """)

    # Migrate legacy Location Pick.pick_list to Location Pick Source child rows.
    # During pre-model-sync on new installs, the child table may not exist yet.
    if not _table_exists("tabLocation Pick Source"):
        frappe.db.commit()
        return

    has_legacy = frappe.db.sql(
        "SHOW COLUMNS FROM `tabLocation Pick` LIKE 'pick_list'"
    )
    if not has_legacy:
        frappe.db.commit()
        return

    picks = frappe.db.sql(
        "SELECT name, pick_list FROM `tabLocation Pick` WHERE pick_list IS NOT NULL AND pick_list != ''",
        as_dict=True,
    )
    for pick in picks:
        exists = frappe.db.sql("""
            SELECT name
            FROM `tabLocation Pick Source`
            WHERE parent = %s AND pick_list = %s
            LIMIT 1
        """, (pick.name, pick.pick_list))
        if not exists:
            frappe.db.sql("""
                INSERT INTO `tabLocation Pick Source`
                    (name, creation, modified, modified_by, owner, docstatus, idx,
                     parent, parenttype, parentfield, pick_list)
                VALUES
                    (%s, NOW(), NOW(), %s, %s, 0, 1, %s, %s, %s, %s)
            """, (
                frappe.generate_hash(length=10),
                frappe.session.user,
                frappe.session.user,
                pick.name,
                "Location Pick",
                "pick_lists",
                pick.pick_list,
            ))

    frappe.db.commit()
