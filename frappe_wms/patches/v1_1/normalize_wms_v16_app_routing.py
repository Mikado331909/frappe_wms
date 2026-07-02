import frappe


LEGACY_WORKSPACE_NAMES = (
    "wms",
    "Warehouse Managing System",
    "Warehouse Management System",
)

def execute():
    _normalize_wms_workspace()
    _clean_legacy_link_to_values()
    _remove_standalone_wms_dashboard()

    frappe.db.commit()
    frappe.clear_cache()


def _normalize_wms_workspace():
    for legacy_name in LEGACY_WORKSPACE_NAMES:
        if _workspace_exists_exact(legacy_name) and not _workspace_exists_exact("WMS"):
            frappe.rename_doc("Workspace", legacy_name, "WMS", force=True, ignore_permissions=True)
        elif _workspace_exists_exact(legacy_name):
            frappe.delete_doc("Workspace", legacy_name, force=True, ignore_missing=True)

    frappe.db.sql("""
        DELETE FROM `tabWorkspace`
        WHERE (name = 'WMS' OR label = 'WMS' OR title = 'WMS' OR module = 'WMS')
          AND COALESCE(for_user, '') != ''
    """)

    if not frappe.db.exists("Workspace", "WMS"):
        return

    _set_existing_fields("Workspace", "WMS", {
        "public": 1,
        "is_hidden": 0,
        "for_user": "",
        "icon": "package",
        "module": "WMS",
        "label": "WMS",
        "title": "WMS",
        "app": "frappe_wms",
        "type": "Workspace",
        "parent_page": "",
        "restrict_to_domain": "",
        "sequence_id": 7.1,
        "link_type": "",
        "link_to": "",
        "external_link": "",
    })


def _workspace_exists_exact(name):
    return bool(frappe.db.sql(
        "SELECT name FROM `tabWorkspace` WHERE BINARY name = %s LIMIT 1",
        name,
    ))


def _clean_legacy_link_to_values():
    tables = frappe.db.sql_list("""
        SELECT table_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND column_name = 'link_to'
    """)

    for table in tables:
        for legacy_name in LEGACY_WORKSPACE_NAMES:
            frappe.db.sql(
                f"""
                UPDATE `{table}`
                SET link_to = 'WMS'
                WHERE link_to = %(legacy_name)s
                """,
                {"legacy_name": legacy_name},
            )


def _remove_standalone_wms_dashboard():
    """Keep /desk/wms as the only WMS dashboard-like entry point."""
    if not frappe.db.exists("DocType", "Dashboard"):
        return

    if frappe.db.exists("Dashboard", "WMS"):
        frappe.delete_doc("Dashboard", "WMS", force=True, ignore_permissions=True)


def _set_existing_fields(doctype, name, values):
    meta = frappe.get_meta(doctype)
    existing_values = {
        fieldname: value
        for fieldname, value in values.items()
        if meta.has_field(fieldname)
    }

    if existing_values:
        frappe.db.set_value(doctype, name, existing_values)
