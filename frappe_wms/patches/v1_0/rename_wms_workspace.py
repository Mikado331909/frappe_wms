import frappe


def execute():
    """
    Rename workspace 'WMS' → 'wms' so Frappe routes the desk tile to /desk/wms.
    Frappe uses the workspace name as-is in the URL; uppercase 'WMS' resolves to
    /desk/WMS which triggers a 'Page WMS not found' error before the workspace
    can be rendered. The fixture now syncs the record under the lowercase name.
    """
    if frappe.db.exists("Workspace", "WMS") and not frappe.db.exists("Workspace", "wms"):
        frappe.rename_doc("Workspace", "WMS", "wms", force=True, ignore_permissions=True)
    elif frappe.db.exists("Workspace", "WMS"):
        frappe.delete_doc("Workspace", "WMS", force=True, ignore_missing=True)
