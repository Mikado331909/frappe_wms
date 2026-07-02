import frappe


def execute():
    """Show WMS as a module tile on the Desk home page."""
    if not frappe.db.exists("Workspace", "WMS"):
        return

    values = {
        "public": 1,
        "is_hidden": 0,
        "for_user": "",
        "module": "WMS",
        "label": "WMS",
        "title": "WMS",
        "app": "frappe_wms",
        "type": "Workspace",
        "category": "Modules",
        "indicator_color": "blue",
        "icon": "package",
        "parent_page": "",
        "link_type": "",
        "link_to": "",
        "external_link": "",
        "restrict_to_domain": "",
        "sequence_id": 7.1,
    }

    meta = frappe.get_meta("Workspace")
    existing_values = {
        fieldname: value
        for fieldname, value in values.items()
        if meta.has_field(fieldname)
    }
    if existing_values:
        frappe.db.set_value("Workspace", "WMS", existing_values)

    frappe.db.commit()
    frappe.clear_cache()
