"""
Pick Performance rapport — gepickte vs vereiste hoeveelheden per picker per periode.
"""
import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    return _columns(), _get_data(filters)


def _columns():
    return [
        {"label": "Datum", "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": "Location Pick", "fieldname": "location_pick", "fieldtype": "Link", "options": "Location Pick", "width": 160},
        {"label": "Picker", "fieldname": "picker", "fieldtype": "Link", "options": "User", "width": 150},
        {"label": "Pick Lists", "fieldname": "pick_lists", "fieldtype": "Data", "width": 200},
        {"label": "Regels", "fieldname": "line_count", "fieldtype": "Int", "width": 70},
        {"label": "Vereist", "fieldname": "total_required", "fieldtype": "Float", "width": 90},
        {"label": "Gepickt", "fieldname": "total_picked", "fieldtype": "Float", "width": 90},
        {"label": "Volledigheid %", "fieldname": "completeness_pct", "fieldtype": "Percent", "width": 110},
        {"label": "Afwijkingen", "fieldname": "discrepancies", "fieldtype": "Int", "width": 90},
    ]


def _get_data(filters):
    conditions = []
    values = {}

    if filters.get("from_date"):
        conditions.append("lp.posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("lp.posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]
    if filters.get("picker"):
        conditions.append("lp.picker = %(picker)s")
        values["picker"] = filters["picker"]

    conditions.append("lp.docstatus = 1")
    where = "WHERE " + " AND ".join(conditions)

    picks = frappe.db.sql(f"""
        SELECT
            lp.name AS location_pick,
            lp.posting_date,
            lp.picker,
            SUM(lpl.required_qty) AS total_required,
            SUM(COALESCE(lpl.picked_qty, 0)) AS total_picked,
            COUNT(lpl.name) AS line_count,
            SUM(CASE WHEN ABS(COALESCE(lpl.picked_qty, 0) - lpl.required_qty) > 0.001 THEN 1 ELSE 0 END) AS discrepancies
        FROM `tabLocation Pick` lp
        INNER JOIN `tabLocation Pick Line` lpl ON lpl.parent = lp.name
        {where}
        GROUP BY lp.name
        ORDER BY lp.posting_date DESC
    """, values, as_dict=True)

    # Haal pick lists per Location Pick op
    pick_lists_map = {}
    if picks:
        lp_names = [p.location_pick for p in picks]
        sources = frappe.db.get_all(
            "Location Pick Source",
            filters={"parent": ["in", lp_names]},
            fields=["parent", "pick_list"],
        )
        for s in sources:
            pick_lists_map.setdefault(s.parent, []).append(s.pick_list)

    data = []
    for pick in picks:
        req = flt(pick.total_required)
        picked = flt(pick.total_picked)
        pct = round(picked / req * 100, 1) if req > 0 else 0
        data.append({
            "posting_date": pick.posting_date,
            "location_pick": pick.location_pick,
            "picker": pick.picker,
            "pick_lists": ", ".join(pick_lists_map.get(pick.location_pick, [])),
            "line_count": pick.line_count or 0,
            "total_required": flt(req, 3),
            "total_picked": flt(picked, 3),
            "completeness_pct": pct,
            "discrepancies": pick.discrepancies or 0,
        })
    return data
