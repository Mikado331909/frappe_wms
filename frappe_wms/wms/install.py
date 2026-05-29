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
    Clear all stored desktop customisation for the current user so Frappe
    regenerates the home screen from all public workspaces (including WMS).
    Checks tabWorkspace (for_user rows), tabDefaultValue, and User desk_settings.
    """
    user = frappe.session.user
    results = {}

    # 1. Delete Workspace for_user rows
    ws_rows = frappe.db.sql_list(
        "SELECT name FROM `tabWorkspace` WHERE for_user = %s", user
    )
    if ws_rows:
        frappe.db.sql("DELETE FROM `tabWorkspace` WHERE for_user = %s", user)
    results["workspace_rows_deleted"] = ws_rows

    # 2. Clear DefaultValue entries related to desktop/workspace
    dv_rows = frappe.db.sql("""
        SELECT name, defkey FROM `tabDefaultValue`
        WHERE parent = %s
          AND (defkey LIKE '%%desktop%%' OR defkey LIKE '%%workspace%%' OR defkey LIKE '%%desk%%')
    """, user, as_dict=True)
    if dv_rows:
        for r in dv_rows:
            frappe.db.sql(
                "DELETE FROM `tabDefaultValue` WHERE name = %s", r.name
            )
    results["default_values_deleted"] = [r.defkey for r in dv_rows]

    # 3. Show ALL DefaultValue keys for this user (so we can see what's there)
    all_dv = frappe.db.sql("""
        SELECT defkey, defvalue FROM `tabDefaultValue`
        WHERE parent = %s
        LIMIT 50
    """, user, as_dict=True)
    results["all_user_defaults"] = all_dv

    # 4. Check User document for desk_settings field
    desk_settings = frappe.db.get_value("User", user, "desk_settings") or None
    results["user_desk_settings"] = desk_settings[:200] if desk_settings else None

    frappe.db.commit()
    results["message"] = "Done. Hard-refresh with Ctrl+Shift+R"
    return results
