"""
Fase 1 fundament patch:
- Voegt zone + max_qty toe aan Storage Location
- Voegt zone toe aan Batch Location Stock (backfill)
- Voegt movement_type toe aan Batch Location Movement
- Voegt pick_list toe aan Location Pick Line (backfill vanuit Pick List Item)
- Migreert Location Pick.pick_list → Location Pick Source child tabel
"""
import frappe


def execute():
    # ------------------------------------------------------------------
    # Storage Location: zone + max_qty
    # ------------------------------------------------------------------
    for col, dtype in [("zone", "varchar(140)"), ("max_qty", "decimal(21,9) default 0")]:
        if not frappe.db.has_column("Storage Location", col):
            frappe.db.add_column("Storage Location", col, dtype)

    # ------------------------------------------------------------------
    # Batch Location Stock: zone
    # ------------------------------------------------------------------
    if not frappe.db.has_column("Batch Location Stock", "zone"):
        frappe.db.add_column("Batch Location Stock", "zone", "varchar(140)")

    # Backfill zone vanuit Storage Location
    frappe.db.sql("""
        UPDATE `tabBatch Location Stock` bls
        INNER JOIN `tabStorage Location` sl ON sl.name = bls.storage_location
        SET bls.zone = sl.zone
        WHERE sl.zone IS NOT NULL AND sl.zone != ''
          AND (bls.zone IS NULL OR bls.zone = '')
    """)

    # ------------------------------------------------------------------
    # Batch Location Movement: movement_type
    # ------------------------------------------------------------------
    if not frappe.db.has_column("Batch Location Movement", "movement_type"):
        frappe.db.add_column("Batch Location Movement", "movement_type", "varchar(50)")

    # Backfill bestaande inbound movements
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

    # ------------------------------------------------------------------
    # Location Pick Line: pick_list
    # ------------------------------------------------------------------
    if not frappe.db.has_column("Location Pick Line", "pick_list"):
        frappe.db.add_column("Location Pick Line", "pick_list", "varchar(140)")

    # Backfill vanuit Pick List Item → parent (Pick List)
    frappe.db.sql("""
        UPDATE `tabLocation Pick Line` lpl
        INNER JOIN `tabPick List Item` pli ON pli.name = lpl.pick_list_item
        SET lpl.pick_list = pli.parent
        WHERE (lpl.pick_list IS NULL OR lpl.pick_list = '')
          AND pli.parent IS NOT NULL
    """)

    # ------------------------------------------------------------------
    # Location Pick → Location Pick Source migratie
    # ------------------------------------------------------------------
    # Frappe's migrate heeft de nieuwe tabel al aangemaakt via de JSON.
    # We lezen de legacy pick_list kolom en maken child-rijen aan.
    if not frappe.db.has_column("Location Pick", "pick_list"):
        return  # Niets te migreren

    picks = frappe.db.sql(
        "SELECT name, pick_list FROM `tabLocation Pick` WHERE pick_list IS NOT NULL AND pick_list != ''",
        as_dict=True,
    )
    for pick in picks:
        exists = frappe.db.exists(
            "Location Pick Source",
            {"parent": pick.name, "pick_list": pick.pick_list},
        )
        if not exists:
            frappe.get_doc({
                "doctype": "Location Pick Source",
                "parent": pick.name,
                "parenttype": "Location Pick",
                "parentfield": "pick_lists",
                "pick_list": pick.pick_list,
            }).insert(ignore_permissions=True)
