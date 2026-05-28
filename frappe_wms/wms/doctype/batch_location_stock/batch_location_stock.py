import frappe
from frappe import _
from frappe.model.document import Document


class BatchLocationStock(Document):
    def validate(self):
        self._validate_location_warehouse_match()
        self._check_duplicate()
        self._validate_qty_against_erpnext()

    def _validate_location_warehouse_match(self):
        loc_warehouse = frappe.db.get_value(
            "Storage Location", self.storage_location, "warehouse"
        )
        if loc_warehouse and loc_warehouse != self.warehouse:
            frappe.throw(
                _(
                    "Storage Location {0} belongs to warehouse {1}, not {2}."
                ).format(self.storage_location, loc_warehouse, self.warehouse)
            )

    def _check_duplicate(self):
        existing = frappe.db.get_value(
            "Batch Location Stock",
            {
                "item_code": self.item_code,
                "batch_no": self.batch_no,
                "warehouse": self.warehouse,
                "storage_location": self.storage_location,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _(
                    "A Batch Location Stock record already exists for Item {0}, "
                    "Batch {1}, Warehouse {2}, Location {3}: {4}."
                ).format(
                    self.item_code,
                    self.batch_no,
                    self.warehouse,
                    self.storage_location,
                    existing,
                )
            )

    def _validate_qty_against_erpnext(self):
        if not frappe.db.get_single_value("WMS Settings", "validate_against_erpnext"):
            return
        if self.qty < 0:
            frappe.throw(_("Qty cannot be negative."))

        erpnext_qty = _get_erpnext_batch_qty(
            self.item_code, self.batch_no, self.warehouse
        )
        other_location_qty = (
            frappe.db.sql(
                """
                SELECT COALESCE(SUM(qty), 0)
                FROM `tabBatch Location Stock`
                WHERE item_code = %s AND batch_no = %s AND warehouse = %s
                  AND name != %s
            """,
                (self.item_code, self.batch_no, self.warehouse, self.name),
            )[0][0]
            or 0.0
        )
        total = other_location_qty + self.qty
        if total > erpnext_qty + 0.001:
            frappe.throw(
                _(
                    "Total location qty {0} for Item {1}, Batch {2}, Warehouse {3} "
                    "would exceed ERPNext stock of {4}."
                ).format(
                    frappe.utils.flt(total, 3),
                    self.item_code,
                    self.batch_no,
                    self.warehouse,
                    frappe.utils.flt(erpnext_qty, 3),
                )
            )


def _get_erpnext_batch_qty(item_code, batch_no, warehouse):
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM(actual_qty), 0)
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s AND batch_no = %s AND warehouse = %s
          AND is_cancelled = 0
    """,
        (item_code, batch_no, warehouse),
    )
    return frappe.utils.flt(result[0][0]) if result else 0.0
