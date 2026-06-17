import frappe


CUSTOM_FIELD_UPDATES = {
    "Batch-customer": {
        "label": "Customer (WMS)",
        "description": "Customer that owns this batch for WMS segregation.",
    },
    "Purchase Receipt Item-wms_customer": {
        "label": "Customer (WMS)",
        "description": "Customer for whom this line is received. Copied to WMS location stock.",
    },
    "Purchase Receipt Item-wms_require_qc": {
        "label": "QC Required",
        "description": "If checked: the item goes to a QC Hold location and a WMS QC Check is created.",
    },
    "Purchase Receipt Item-wms_cross_dock": {
        "label": "Cross-dock",
        "description": "If checked: the item goes to a Cross-dock Staging location for direct flow-through.",
    },
    "Purchase Receipt Item-wms_cross_dock_so": {
        "label": "Cross-dock Sales Order",
        "description": "Linked Sales Order for this cross-dock shipment.",
    },
}

SELECT_VALUE_UPDATES = {
    "WMS QC Check": {
        "check_type": {
            "Kwaliteit": "Quality",
            "Kwantiteit": "Quantity",
            "Beide": "Both",
        }
    },
    "WMS QC Check Line": {
        "outcome": {
            "Goedgekeurd": "Approved",
            "Afgekeurd": "Rejected",
            "Gedeeltelijk": "Partial",
        }
    },
}


def execute():
    _update_custom_fields()
    _update_select_values()
    frappe.clear_cache()


def _update_custom_fields():
    for name, values in CUSTOM_FIELD_UPDATES.items():
        if frappe.db.exists("Custom Field", name):
            frappe.db.set_value("Custom Field", name, values)


def _update_select_values():
    for doctype, fields in SELECT_VALUE_UPDATES.items():
        if not frappe.db.exists("DocType", doctype):
            continue

        if not frappe.db.table_exists(doctype):
            continue

        table = f"tab{doctype}"
        for fieldname, replacements in fields.items():
            for old_value, new_value in replacements.items():
                frappe.db.sql(
                    f"""
                    UPDATE `{table}`
                    SET `{fieldname}` = %(new_value)s
                    WHERE `{fieldname}` = %(old_value)s
                    """,
                    {"old_value": old_value, "new_value": new_value},
                )
