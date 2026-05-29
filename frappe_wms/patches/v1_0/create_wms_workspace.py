"""
Create the WMS Workspace if it doesn't already exist.
Runs once during bench migrate.
"""
import frappe
import json


def execute():
    if frappe.db.exists("Workspace", "WMS"):
        # Update existing workspace to ensure it's up to date
        frappe.db.set_value("Workspace", "WMS", {
            "public": 1,
            "is_hidden": 0,
            "icon": "package",
            "module": "WMS",
            "label": "WMS",
            "title": "WMS",
            "sequence_id": 99,
        })
        return

    content = json.dumps([
        {"id": "wms_sc1", "type": "shortcut", "data": {"shortcut_name": "Location Pick", "col": 3}},
        {"id": "wms_sc2", "type": "shortcut", "data": {"shortcut_name": "Batch Location Stock", "col": 3}},
        {"id": "wms_sc3", "type": "shortcut", "data": {"shortcut_name": "Storage Location", "col": 3}},
        {"id": "wms_card1", "type": "card", "data": {"card_name": "Transactions", "col": 4}},
        {"id": "wms_card2", "type": "card", "data": {"card_name": "Setup", "col": 4}},
        {"id": "wms_card3", "type": "card", "data": {"card_name": "Reports", "col": 4}},
    ])

    workspace = frappe.get_doc({
        "doctype": "Workspace",
        "name": "WMS",
        "label": "WMS",
        "title": "WMS",
        "module": "WMS",
        "icon": "package",
        "public": 1,
        "is_hidden": 0,
        "sequence_id": 99,
        "content": content,
        "shortcuts": [
            {"type": "DocType", "label": "Location Pick",       "link_to": "Location Pick",       "color": "Blue",  "format": "{} Open", "stats_filter": '{"status": "Open"}'},
            {"type": "DocType", "label": "Batch Location Stock","link_to": "Batch Location Stock","color": "Green"},
            {"type": "DocType", "label": "Storage Location",    "link_to": "Storage Location",    "color": "Grey"},
        ],
        "links": [
            {"type": "Link", "label": "Location Pick",            "link_type": "DocType", "link_to": "Location Pick",            "parent_label": "Transactions", "onboard": 1},
            {"type": "Link", "label": "Batch Location Stock",     "link_type": "DocType", "link_to": "Batch Location Stock",     "parent_label": "Transactions", "onboard": 1},
            {"type": "Link", "label": "Batch Location Movement",  "link_type": "DocType", "link_to": "Batch Location Movement",  "parent_label": "Transactions", "onboard": 0},
            {"type": "Link", "label": "Storage Location",         "link_type": "DocType", "link_to": "Storage Location",         "parent_label": "Setup",        "onboard": 1},
            {"type": "Link", "label": "WMS Settings",             "link_type": "DocType", "link_to": "WMS Settings",             "parent_label": "Setup",        "onboard": 0},
            {"type": "Link", "label": "Location Pick Lines",      "link_type": "Report",  "link_to": "Location Pick Lines",      "parent_label": "Reports",      "is_query_report": 1},
            {"type": "Link", "label": "Location Stock Reconciliation", "link_type": "Report", "link_to": "Location Stock Reconciliation", "parent_label": "Reports", "is_query_report": 1},
        ],
    })
    workspace.insert(ignore_permissions=True)
    frappe.db.commit()
