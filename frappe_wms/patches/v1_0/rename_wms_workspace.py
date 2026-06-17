import frappe


def execute():
    """
    Keep the WMS workspace record name aligned with standard ERPNext modules.

    ERPNext workspaces such as Stock use a lowercase export path, but the
    Workspace document name remains title-cased. Older WMS builds briefly used
    the lowercase document name "wms"; move that back to "WMS".
    """
    if frappe.db.exists("Workspace", "wms") and not frappe.db.exists("Workspace", "WMS"):
        frappe.rename_doc("Workspace", "wms", "WMS", force=True, ignore_permissions=True)
    elif frappe.db.exists("Workspace", "wms"):
        frappe.delete_doc("Workspace", "wms", force=True, ignore_missing=True)
