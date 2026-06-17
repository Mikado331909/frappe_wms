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
           OR name IN ('WMS', 'wms')
           OR label = 'WMS'
        ORDER BY for_user, sequence_id
    """, {"user": user}, as_dict=True)
    return {"user": user, "records": records}


@frappe.whitelist()
def diagnose_wms_workspace():
    """
    Deep diagnostic: checks Module Def, blocked modules, and calls
    get_workspace_sidebar_items to see if WMS appears in the list.
    """
    user = frappe.session.user
    result = {}

    # 1. Exact WMS workspace DB values
    wms_ws = frappe.db.sql("""
        SELECT name, label, title, public, is_hidden,
               COALESCE(for_user, '__NULL__') AS for_user_val,
               module, sequence_id, restrict_to_domain
        FROM `tabWorkspace`
        WHERE name IN ('WMS', 'wms')
    """, as_dict=True)
    result["wms_workspace_db"] = wms_ws

    # 2. Module Def records for WMS
    module_def = frappe.db.sql("""
        SELECT name, module_name, app_name
        FROM `tabModule Def`
        WHERE module_name = 'WMS' OR app_name = 'frappe_wms'
    """, as_dict=True)
    result["module_def_records"] = module_def

    # 3. User's blocked modules
    try:
        user_doc = frappe.get_cached_doc("User", user)
        blocked = user_doc.get_blocked_modules() if hasattr(user_doc, "get_blocked_modules") else []
    except Exception as e:
        blocked = f"Error: {e}"
    result["blocked_modules"] = blocked

    # 4. Active domains
    try:
        active_domains = frappe.get_active_domains()
    except Exception as e:
        active_domains = f"Error: {e}"
    result["active_domains"] = active_domains

    # 5. Call get_workspace_sidebar_items and see if WMS is in the list
    try:
        from frappe.desk.desktop import get_workspace_sidebar_items
        sidebar = get_workspace_sidebar_items()
        # sidebar is typically {"pages": [...], ...}
        if isinstance(sidebar, dict):
            pages = sidebar.get("pages", sidebar.get("workspaces", []))
        else:
            pages = sidebar or []
        wms_in_sidebar = [
            p for p in pages
            if (p.get("name") in ("WMS", "wms") or p.get("label") == "WMS")
        ]
        result["sidebar_pages_count"] = len(pages)
        result["sidebar_page_names"] = [p.get("name") or p.get("label") for p in pages]
        result["wms_in_sidebar"] = wms_in_sidebar
    except Exception as e:
        result["sidebar_error"] = str(e)

    # 6. Check frappe.local.module_app for WMS
    try:
        module_app = frappe.local.module_app if hasattr(frappe.local, "module_app") else {}
        result["wms_in_module_app"] = module_app.get("wms") or module_app.get("WMS") or "NOT FOUND"
        result["module_app_keys"] = list(module_app.keys())[:20]
    except Exception as e:
        result["module_app_error"] = str(e)

    return result


@frappe.whitelist()
def fix_wms_workspace():
    """
    Force-fixes the WMS workspace so it appears on the desk:
    1. Sets public=1, is_hidden=0, for_user='' on WMS workspace
    2. Clears Frappe cache
    3. Returns the result of get_workspace_sidebar_items to confirm
    """
    result = {}

    # 1. Hard-set the WMS workspace fields
    updated = frappe.db.sql("""
        UPDATE `tabWorkspace`
        SET public    = 1,
            is_hidden = 0,
            for_user  = ''
        WHERE name IN ('WMS', 'wms')
    """)
    result["update_rows"] = "done"

    # 2. Clear the Frappe cache (redis)
    try:
        frappe.clear_cache()
        result["cache_cleared"] = True
    except Exception as e:
        result["cache_clear_error"] = str(e)

    frappe.db.commit()

    # 3. Run get_workspace_sidebar_items to confirm WMS appears
    try:
        from frappe.desk.desktop import get_workspace_sidebar_items
        sidebar = get_workspace_sidebar_items()
        if isinstance(sidebar, dict):
            pages = sidebar.get("pages", sidebar.get("workspaces", []))
        else:
            pages = sidebar or []
        wms_found = any(
            p.get("name") in ("WMS", "wms") or p.get("label") == "WMS"
            for p in pages
        )
        result["sidebar_page_names"] = [p.get("name") or p.get("label") for p in pages]
        result["wms_now_in_sidebar"] = wms_found
    except Exception as e:
        result["sidebar_error"] = str(e)

    result["message"] = "Done – now do Ctrl+Shift+R to reload the desk"
    return result


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

    # 4. Check tabUser Settings (Frappe per-user per-page settings)
    user_settings_rows = frappe.db.sql("""
        SELECT `user`, `doctype`, SUBSTR(`data`, 1, 300) AS data_preview
        FROM `__UserSettings`
        WHERE `user` = %s
        LIMIT 20
    """, user, as_dict=True)
    results["user_settings_rows"] = user_settings_rows

    # 5. Show ALL workspaces with their for_user value to understand the pattern
    all_ws = frappe.db.sql("""
        SELECT name, label, is_hidden, public, sequence_id,
               COALESCE(for_user, '__NULL__') AS for_user_val
        FROM `tabWorkspace`
        ORDER BY sequence_id
        LIMIT 30
    """, as_dict=True)
    results["all_workspaces"] = all_ws

    # 6. Fix: ensure WMS is public with correct for_user
    frappe.db.sql("""
        UPDATE `tabWorkspace`
        SET for_user = '', public = 1, is_hidden = 0
        WHERE name IN ('WMS', 'wms')
    """)
    results["wms_fixed"] = "Set public=1, is_hidden=0, for_user='' on WMS workspace"

    # 7. Clear cache
    try:
        frappe.clear_cache()
        results["cache_cleared"] = True
    except Exception as e:
        results["cache_clear_error"] = str(e)

    frappe.db.commit()
    results["message"] = "Done. Hard-refresh with Ctrl+Shift+R"
    return results
