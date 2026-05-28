import frappe


def execute(filters=None):
    filters = filters or {}
    columns = _columns()
    data = _get_data(filters)
    return columns, data


def _columns():
    return [
        {
            "label": "Location Pick",
            "fieldname": "location_pick",
            "fieldtype": "Link",
            "options": "Location Pick",
            "width": 160,
        },
        {
            "label": "Status",
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 90,
        },
        {
            "label": "Posting Date",
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": "Pick List",
            "fieldname": "pick_list",
            "fieldtype": "Link",
            "options": "Pick List",
            "width": 160,
        },
        {
            "label": "Picker",
            "fieldname": "picker",
            "fieldtype": "Link",
            "options": "User",
            "width": 140,
        },
        {
            "label": "Item Code",
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 140,
        },
        {
            "label": "Item Name",
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": "Batch No",
            "fieldname": "batch_no",
            "fieldtype": "Link",
            "options": "Batch",
            "width": 120,
        },
        {
            "label": "Warehouse",
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 150,
        },
        {
            "label": "Source Location",
            "fieldname": "source_location",
            "fieldtype": "Link",
            "options": "Storage Location",
            "width": 140,
        },
        {
            "label": "Required Qty",
            "fieldname": "required_qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "label": "Picked Qty",
            "fieldname": "picked_qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "label": "UOM",
            "fieldname": "uom",
            "fieldtype": "Link",
            "options": "UOM",
            "width": 70,
        },
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
    if filters.get("status"):
        conditions.append("lp.status = %(status)s")
        values["status"] = filters["status"]
    if filters.get("warehouse"):
        conditions.append("lpl.warehouse = %(warehouse)s")
        values["warehouse"] = filters["warehouse"]
    if filters.get("item_code"):
        conditions.append("lpl.item_code = %(item_code)s")
        values["item_code"] = filters["item_code"]
    if filters.get("pick_list"):
        conditions.append("lp.pick_list = %(pick_list)s")
        values["pick_list"] = filters["pick_list"]

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    return frappe.db.sql(
        f"""
        SELECT
            lpl.parent          AS location_pick,
            lp.status,
            lp.posting_date,
            lp.pick_list,
            lp.picker,
            lpl.item_code,
            i.item_name,
            lpl.batch_no,
            lpl.warehouse,
            lpl.source_location,
            lpl.required_qty,
            lpl.picked_qty,
            lpl.uom
        FROM `tabLocation Pick Line` lpl
        INNER JOIN `tabLocation Pick` lp ON lp.name = lpl.parent
        LEFT  JOIN `tabItem`          i  ON i.name  = lpl.item_code
        {where}
        ORDER BY lp.posting_date DESC, lp.name, lpl.idx
        """,
        values,
        as_dict=True,
    )
