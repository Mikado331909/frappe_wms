import frappe


def execute():
    """Remove the duplicate /desk/dashboard-view/WMS entry.

    The WMS Workspace at /desk/wms remains the single operational dashboard.
    Number Cards and Dashboard Charts are kept because the workspace uses them.
    """
    if not frappe.db.exists("DocType", "Dashboard"):
        return

    if frappe.db.exists("Dashboard", "WMS"):
        frappe.delete_doc("Dashboard", "WMS", force=True, ignore_permissions=True)

    frappe.db.commit()
    frappe.clear_cache()
