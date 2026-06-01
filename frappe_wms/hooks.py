app_name = "frappe_wms"

fixtures = [
    {"doctype": "Workspace", "filters": [["name", "in", ["WMS"]]]},
    {"doctype": "Custom Field", "filters": [["dt", "=", "Purchase Receipt Item"], ["fieldname", "=", "wms_customer"]]},
]
app_title = "Frappe WMS"
app_publisher = "Your Company"
app_description = "Lightweight WMS location layer for ERPNext"
app_email = "admin@example.com"
app_license = "MIT"
app_version = "0.0.1"

# ------------------------------------------------------------
# DocType events
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
# Client-side JS extensions for standard ERPNext DocTypes
# ------------------------------------------------------------
doctype_js = {
    "Pick List": "public/js/pick_list.js",
    "Batch Location Stock": "public/js/batch_location_stock.js",
    "Location Pick": "public/js/location_pick.js",
}

doctype_list_js = {
    "Batch Location Stock": "public/js/batch_location_stock_list.js",
}
