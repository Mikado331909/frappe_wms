"""
Installation helpers for Frappe WMS.

The whitelisted workspace-debugging endpoints that previously lived in this
module (debug_workspace_info, diagnose_wms_workspace, fix_wms_workspace,
reset_my_desktop) have been removed: they were unauthenticated-role endpoints
performing raw UPDATE/DELETE statements on tabWorkspace and tabDefaultValue
with explicit commits, callable by any logged-in user. Workspace setup is
handled by patches; ad-hoc diagnostics belong in a bench console session.
"""
