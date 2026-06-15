app_name = "frappe_wms"

fixtures = [
    {"doctype": "Workspace", "filters": [["name", "in", ["WMS"]]]},
    {
        "doctype": "Custom Field",
        "filters": [[
            "dt", "=", "Purchase Receipt Item"
        ], [
            "fieldname", "in", [
                "wms_customer", "wms_require_qc", "wms_cross_dock", "wms_cross_dock_so"
            ]
        ]],
    },
    {
        "doctype": "Custom Field",
        "filters": [["dt", "=", "Batch"], ["fieldname", "=", "customer"]],
    },
    {
        "doctype": "Number Card",
        "filters": [["name", "in", [
            "Pending QC Checks", "Cross-dock Pending", "Active Storage Locations"
        ]]],
    },
    {
        "doctype": "Dashboard Chart",
        "filters": [["name", "in", ["Warehouse Movements by Type"]]],
    },
]

app_title = "Frappe WMS"
app_publisher = "Frappe WMS"
app_description = "Lightweight WMS location layer for ERPNext"
app_email = "admin@example.com"
app_license = "MIT"
app_version = "0.2.0"

# ------------------------------------------------------------
# DocType events (ERPNext core documents)
# ------------------------------------------------------------
doc_events = {
    "Purchase Receipt": {
        "on_submit": "frappe_wms.wms.events.purchase_receipt.on_submit",
        "on_cancel": "frappe_wms.wms.events.purchase_receipt.on_cancel",
    },
    "Stock Entry": {
        "on_submit": "frappe_wms.wms.events.stock_entry.on_submit",
    },
    "Delivery Note": {
        "on_submit": "frappe_wms.wms.events.delivery_note.on_submit",
    },
}

# ------------------------------------------------------------
# Client-side JS extensions
# ------------------------------------------------------------
doctype_js = {
    "Pick List":            "public/js/pick_list.js",
    "Batch Location Stock": "public/js/batch_location_stock.js",
    "Location Pick":        "public/js/location_pick.js",
    "Purchase Receipt":     "public/js/purchase_receipt.js",
    "WMS QC Check":         "public/js/wms_qc_check.js",
    "WMS Cross Dock":       "public/js/wms_cross_dock.js",
    "WMS Cycle Count":      "public/js/wms_cycle_count.js",
}

doctype_list_js = {
    "Batch Location Stock": "public/js/batch_location_stock_list.js",
}
