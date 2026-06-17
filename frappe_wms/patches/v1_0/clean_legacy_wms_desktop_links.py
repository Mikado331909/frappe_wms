import frappe


LEGACY_NAMES = (
    "Warehouse Managing System",
    "Warehouse Management System",
)


def execute():
    """
    Remove old desktop/workspace references to legacy WMS page names.

    Some early installs can keep child rows that point to "Warehouse Managing
    System". Frappe validates those rows when adding the workspace to the
    desktop, but that target does not exist anymore, so the action fails and
    the module breadcrumb can keep falling back to the first WMS DocType.
    """
    _rename_legacy_workspace_records()
    _clean_workspace_child_links()
    _fix_wms_workspace()

    frappe.db.commit()
    frappe.clear_cache()


def _rename_legacy_workspace_records():
    for legacy_name in LEGACY_NAMES:
        if frappe.db.exists("Workspace", legacy_name) and not frappe.db.exists("Workspace", "WMS"):
            frappe.rename_doc("Workspace", legacy_name, "WMS", force=True, ignore_permissions=True)
        elif frappe.db.exists("Workspace", legacy_name):
            frappe.delete_doc("Workspace", legacy_name, force=True, ignore_missing=True)


def _clean_workspace_child_links():
    replacements = {
        "Workspace Link": {
            "link_type": "Workspace",
            "link_to": "WMS",
        },
        "Workspace Shortcut": {
            "type": "Workspace",
            "link_to": "WMS",
        },
    }

    for doctype, values in replacements.items():
        table = f"tab{doctype}"
        if not frappe.db.table_exists(table):
            continue

        for legacy_name in LEGACY_NAMES:
            frappe.db.sql(
                f"""
                UPDATE `{table}`
                SET link_to = %(link_to)s
                WHERE link_to = %(legacy_name)s
                """,
                {"link_to": values["link_to"], "legacy_name": legacy_name},
            )

        meta = frappe.get_meta(doctype)
        for fieldname, value in values.items():
            if meta.has_field(fieldname):
                frappe.db.sql(
                    f"""
                    UPDATE `{table}`
                    SET `{fieldname}` = %(value)s
                    WHERE parent = 'WMS'
                      AND link_to = 'WMS'
                    """,
                    {"value": value},
                )


def _fix_wms_workspace():
    if frappe.db.exists("Workspace", "WMS"):
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
