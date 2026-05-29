"""
Add the WMS workspace to every user who has a personalised Frappe desktop.

When a user has customised their home screen, new public workspaces are not
shown automatically.  This patch creates a user-specific Workspace record
(for_user = <user>) for each such user so WMS appears on their home screen.
"""
import frappe
import json


_CONTENT = json.dumps([
    {"id": "wms_sc1",   "type": "shortcut", "data": {"shortcut_name": "Location Pick",       "col": 3}},
    {"id": "wms_sc2",   "type": "shortcut", "data": {"shortcut_name": "Batch Location Stock", "col": 3}},
    {"id": "wms_sc3",   "type": "shortcut", "data": {"shortcut_name": "Storage Location",     "col": 3}},
    {"id": "wms_card1", "type": "card",     "data": {"card_name": "Transactions", "col": 4}},
    {"id": "wms_card2", "type": "card",     "data": {"card_name": "Setup",        "col": 4}},
    {"id": "wms_card3", "type": "card",     "data": {"card_name": "Reports",      "col": 4}},
])

_SHORTCUTS = [
    {"type": "DocType", "label": "Location Pick",        "link_to": "Location Pick",        "color": "Blue",  "format": "{} Open", "stats_filter": '{"status": "Open"}'},
    {"type": "DocType", "label": "Batch Location Stock", "link_to": "Batch Location Stock", "color": "Green"},
    {"type": "DocType", "label": "Storage Location",     "link_to": "Storage Location",     "color": "Grey"},
]

_LINKS = [
    {"type": "Link", "label": "Location Pick",                "link_type": "DocType", "link_to": "Location Pick",               "parent_label": "Transactions", "onboard": 1},
    {"type": "Link", "label": "Batch Location Stock",         "link_type": "DocType", "link_to": "Batch Location Stock",        "parent_label": "Transactions", "onboard": 1},
    {"type": "Link", "label": "Batch Location Movement",      "link_type": "DocType", "link_to": "Batch Location Movement",     "parent_label": "Transactions", "onboard": 0},
    {"type": "Link", "label": "Storage Location",             "link_type": "DocType", "link_to": "Storage Location",            "parent_label": "Setup",        "onboard": 1},
    {"type": "Link", "label": "WMS Settings",                 "link_type": "DocType", "link_to": "WMS Settings",                "parent_label": "Setup",        "onboard": 0},
    {"type": "Link", "label": "Location Pick Lines",          "link_type": "Report",  "link_to": "Location Pick Lines",         "parent_label": "Reports",      "is_query_report": 1},
    {"type": "Link", "label": "Location Stock Reconciliation","link_type": "Report",  "link_to": "Location Stock Reconciliation","parent_label": "Reports",     "is_query_report": 1},
]


def execute():
    users = frappe.db.sql_list("""
        SELECT DISTINCT for_user
        FROM `tabWorkspace`
        WHERE for_user IS NOT NULL AND for_user != ''
    """)

    for user in users:
        if frappe.db.exists("Workspace", {"for_user": user, "label": "WMS"}):
            continue

        max_seq = frappe.db.sql("""
            SELECT COALESCE(MAX(sequence_id), 100)
            FROM `tabWorkspace`
            WHERE for_user = %s
        """, user)[0][0]

        ws = frappe.new_doc("Workspace")
        ws.title       = "WMS"
        ws.label       = "WMS"
        ws.icon        = "package"
        ws.module      = "WMS"
        ws.for_user    = user
        ws.public      = 0
        ws.is_hidden   = 0
        ws.sequence_id = float(max_seq) + 1
        ws.content     = _CONTENT
        for sc in _SHORTCUTS:
            ws.append("shortcuts", sc)
        for lnk in _LINKS:
            ws.append("links", lnk)
        ws.insert(ignore_permissions=True)

    frappe.db.commit()
