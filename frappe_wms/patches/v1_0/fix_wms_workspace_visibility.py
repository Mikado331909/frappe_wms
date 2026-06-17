import frappe


def execute():
    """
    Keep the WMS workspace route and visibility consistent.

    Older installs may have a public Workspace named "wms". ERPNext workspaces
    such as Stock use a lowercase export path, but the Workspace document name
    remains title-cased.
    """
    workspace_name = "WMS"
    legacy_name = "wms"

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
            "app": "frappe_wms",
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
