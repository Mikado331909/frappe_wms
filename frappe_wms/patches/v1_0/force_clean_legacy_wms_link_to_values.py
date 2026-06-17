import frappe


LEGACY_NAMES = (
    "Warehouse Managing System",
    "Warehouse Management System",
)


def execute():
    """
    Force-clean legacy WMS Link To values from the database.

    The Workspace UI validates child rows before "Add to Desktop". If any child
    row still has Link To = "Warehouse Managing System", that action fails even
    when the public WMS workspace itself is correct. This patch scans every table
    with a link_to column so it also catches rows created by older/custom desktop
    code paths.
    """
    _replace_legacy_link_to_values()
    _remove_legacy_workspace_records()
    _normalize_wms_workspace()

    frappe.db.commit()
    frappe.clear_cache()


def _replace_legacy_link_to_values():
    tables = frappe.db.sql_list("""
        SELECT table_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND column_name = 'link_to'
    """)

    for table in tables:
        for legacy_name in LEGACY_NAMES:
            frappe.db.sql(
                f"""
                UPDATE `{table}`
                SET link_to = 'WMS'
                WHERE link_to = %(legacy_name)s
                """,
                {"legacy_name": legacy_name},
            )


def _remove_legacy_workspace_records():
    for legacy_name in LEGACY_NAMES:
        if frappe.db.exists("Workspace", legacy_name):
            if not frappe.db.exists("Workspace", "WMS"):
                frappe.rename_doc("Workspace", legacy_name, "WMS", force=True, ignore_permissions=True)
            else:
                frappe.delete_doc("Workspace", legacy_name, force=True, ignore_missing=True)


def _normalize_wms_workspace():
    if not frappe.db.exists("Workspace", "WMS"):
        return

    frappe.db.set_value("Workspace", "WMS", {
        "public": 1,
        "is_hidden": 0,
        "for_user": "",
        "module": "WMS",
        "label": "WMS",
        "title": "WMS",
        "app": "frappe_wms",
        "type": "Workspace",
        "link_type": "",
        "link_to": "",
        "external_link": "",
    })
