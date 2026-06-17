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
    _remove_user_specific_wms_workspaces()
    frappe.db.commit()
    try:
        frappe.clear_cache()
    except Exception:
        pass


def _ensure_public_workspace():
    """Create or update the public WMS workspace."""
    workspace_name = "WMS"
    legacy_name = "wms"

    if frappe.db.exists("Workspace", legacy_name) and not frappe.db.exists("Workspace", workspace_name):
        frappe.rename_doc("Workspace", legacy_name, workspace_name, force=True, ignore_permissions=True)
    elif frappe.db.exists("Workspace", legacy_name):
        frappe.delete_doc("Workspace", legacy_name, force=True, ignore_missing=True)

    if frappe.db.exists("Workspace", workspace_name):
        frappe.db.set_value("Workspace", workspace_name, {
            "public":    1,
            "is_hidden": 0,
            "for_user":  "",
            "icon":      "package",
            "module":    "WMS",
            "label":     "WMS",
            "title":     "WMS",
            "sequence_id": 99,
            "app":       "frappe_wms",
        })
        return

    ws = frappe.get_doc({
        "doctype":     "Workspace",
        "name":        workspace_name,
        "label":       "WMS",
        "title":       "WMS",
        "module":      "WMS",
        "icon":        "package",
        "public":      1,
        "is_hidden":   0,
        "for_user":    "",
        "sequence_id": 99,
        "app":         "frappe_wms",
        "content":     _CONTENT,
        "shortcuts":   _SHORTCUTS,
        "links":       _LINKS,
    })
    ws.insert(ignore_permissions=True)


def _remove_user_specific_wms_workspaces():
    """
    Remove old user-specific WMS workspace rows.

    A public Workspace should be the only WMS entry. User-specific rows can make
    the desktop tile and breadcrumbs fall back to the first shortcut instead of
    opening /desk/wms.
    """
    rows = frappe.db.sql_list("""
        SELECT name
        FROM `tabWorkspace`
        WHERE label = 'WMS'
          AND COALESCE(for_user, '') != ''
    """)

    for name in rows:
        frappe.delete_doc("Workspace", name, force=True, ignore_permissions=True)
