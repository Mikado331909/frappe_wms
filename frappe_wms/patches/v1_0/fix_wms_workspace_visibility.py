import frappe


def execute():
    """
    Keep the WMS workspace route and visibility consistent.

    Older installs may have a public Workspace named "WMS" while the exported
    workspace uses the lowercase route name "wms". Frappe desk routes are
    case-sensitive enough that this can make the sidebar tile disappear or open
    the wrong page after migrations.
    """
    workspace_name = "wms"
    legacy_name = "WMS"

    if frappe.db.exists("Workspace", legacy_name) and not frappe.db.exists("Workspace", workspace_name):
        frappe.rename_doc("Workspace", legacy_name, workspace_name, force=True, ignore_permissions=True)
    elif frappe.db.exists("Workspace", legacy_name):
        frappe.delete_doc("Workspace", legacy_name, force=True, ignore_missing=True)

    if frappe.db.exists("Workspace", workspace_name):
        frappe.db.set_value("Workspace", workspace_name, {
            "public": 1,
            "is_hidden": 0,
            "for_user": "",
            "icon": "package",
            "module": "WMS",
            "label": "WMS",
            "title": "WMS",
        })

    frappe.db.sql("""
        UPDATE `tabWorkspace`
        SET is_hidden = 0,
            module = 'WMS',
            label = 'WMS',
            title = 'WMS'
        WHERE label = 'WMS'
          AND COALESCE(for_user, '') != ''
    """)

    frappe.db.commit()
    frappe.clear_cache()
