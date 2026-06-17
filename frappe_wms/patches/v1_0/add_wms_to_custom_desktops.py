import frappe


def execute():
    """Legacy no-op: WMS should use the public Workspace only."""
    frappe.db.commit()
