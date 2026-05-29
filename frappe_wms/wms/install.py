import frappe


@frappe.whitelist()
def debug_workspace_info():
    """
    Returns all Workspace records for the current user + the WMS public workspace.
    Used to diagnose why WMS does not appear on the home screen.
    """
    user = frappe.session.user
    records = frappe.db.sql("""
        SELECT name, label, title, for_user, is_hidden,
               sequence_id, `extends`, public, module
        FROM `tabWorkspace`
        WHERE for_user = %(user)s
           OR name = 'WMS'
           OR label = 'WMS'
        ORDER BY for_user, sequence_id
    """, {"user": user}, as_dict=True)
    return {"user": user, "records": records}


@frappe.whitelist()
def reset_my_desktop():
    """
    Delete all user-specific Workspace records for the current user.
    This resets the home screen to show all public workspaces (including WMS).
    WARNING: any manual hide/show customisations will be lost.
    """
    user = frappe.session.user
    deleted = frappe.db.sql("""
        SELECT name FROM `tabWorkspace` WHERE for_user = %(user)s
    """, {"user": user}, as_dict=True)

    frappe.db.sql("""
        DELETE FROM `tabWorkspace` WHERE for_user = %(user)s
    """, {"user": user})
    frappe.db.commit()
    return {"deleted": [r.name for r in deleted], "message": "Desktop reset. Hard-refresh the page."}
