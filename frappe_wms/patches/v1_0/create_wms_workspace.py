"""
Create the WMS Workspace and add it to every user's custom desktop.

When a Frappe user has personalised their home screen, new public workspaces
are NOT automatically shown.  Frappe tracks per-user desktop visibility via
Workspace records with `for_user` set.  This patch:
  1. Creates / updates the public WMS workspace.
  2. For every user who has a personalised desktop, inserts a user-specific
     Workspace record so WMS appears on their home screen.
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
    {"type": "Link", "label": "Location Pick",               "link_type": "DocType", "link_to": "Location Pick",               "parent_label": "Transactions", "onboard": 1},
    {"type": "Link", "label": "Batch Location Stock",        "link_type": "DocType", "link_to": "Batch Location Stock",        "parent_label": "Transactions", "onboard": 1},
    {"type": "Link", "label": "Batch Location Movement",     "link_type": "DocType", "link_to": "Batch Location Movement",     "parent_label": "Transactions", "onboard": 0},
    {"type": "Link", "label": "Storage Location",            "link_type": "DocType", "link_to": "Storage Location",            "parent_label": "Setup",        "onboard": 1},
    {"type": "Link", "label": "WMS Settings",                "link_type": "DocType", "link_to": "WMS Settings",                "parent_label": "Setup",        "onboard": 0},
    {"type": "Link", "label": "Location Pick Lines",         "link_type": "Report",  "link_to": "Location Pick Lines",         "parent_label": "Reports",      "is_query_report": 1},
    {"type": "Link", "label": "Location Stock Reconciliation","link_type": "Report", "link_to": "Location Stock Reconciliation","parent_label": "Reports",     "is_query_report": 1},
]


def execute():
    _ensure_public_workspace()
    _add_to_custom_desktops()
    frappe.db.commit()


def _ensure_public_workspace():
    """Create or update the public WMS workspace."""
    if frappe.db.exists("Workspace", "WMS"):
        frappe.db.set_value("Workspace", "WMS", {
            "public":    1,
            "is_hidden": 0,
            "icon":      "package",
            "module":    "WMS",
            "label":     "WMS",
            "title":     "WMS",
            "sequence_id": 99,
        })
        return

    ws = frappe.get_doc({
        "doctype":     "Workspace",
        "name":        "WMS",
        "label":       "WMS",
        "title":       "WMS",
        "module":      "WMS",
        "icon":        "package",
        "public":      1,
        "is_hidden":   0,
        "sequence_id": 99,
        "content":     _CONTENT,
        "shortcuts":   _SHORTCUTS,
        "links":       _LINKS,
    })
    ws.insert(ignore_permissions=True)


def _add_to_custom_desktops():
    """
    For every user who has personalised their Frappe desktop (i.e. has at least
    one Workspace row with for_user set), add a user-specific WMS entry so it
    appears on their home screen alongside the other icons.
    """
    users = frappe.db.sql_list("""
        SELECT DISTINCT for_user
        FROM `tabWorkspace`
        WHERE for_user IS NOT NULL AND for_user != ''
    """)

    for user in users:
        # Skip if this user already has a WMS entry on their desktop
        if frappe.db.exists("Workspace", {"for_user": user, "label": "WMS"}):
            continue

        # Find the highest sequence_id this user already has
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
