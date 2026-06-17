import frappe


def execute():
    """
    Remove user-specific WMS workspace rows.

    These rows were created by older patches to force WMS onto personalized
    desktops. On Frappe v15 they can make the home tile or breadcrumb resolve
    to the first WMS shortcut instead of the public /desk/wms workspace.
    """
    frappe.db.sql("""
        DELETE FROM `tabWorkspace`
        WHERE label = 'WMS'
          AND COALESCE(for_user, '') != ''
    """)

    if frappe.db.exists("Workspace", "WMS"):
        frappe.db.set_value("Workspace", "WMS", {
            "public": 1,
            "is_hidden": 0,
            "for_user": "",
            "module": "WMS",
            "label": "WMS",
            "title": "WMS",
            "app": "frappe_wms",
        })

    frappe.db.commit()
    frappe.clear_cache()
