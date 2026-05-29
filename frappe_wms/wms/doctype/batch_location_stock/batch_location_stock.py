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


@frappe.whitelist()
def force_delete_zero(name):
    """
    Force-delete a Batch Location Stock record that has reached zero qty.
    Uses force=True to bypass Frappe's link-checker (the linked Batch Location
    Movement rows are intentional audit history, not a reason to keep the record).
    """
    doc = frappe.get_doc("Batch Location Stock", name)
    if frappe.utils.flt(doc.qty) > 0.001:
        frappe.throw(_("Cannot force-delete: record still has qty {0}.").format(
            frappe.utils.flt(doc.qty, 3)
        ))
    frappe.db.delete("Batch Location Stock", {"name": name})
    return _("Record {0} deleted.").format(name)


@frappe.whitelist()
def move_stock(source_name, to_location, qty):
    """
    Move qty from one Batch Location Stock record to another location.
    Creates a proper Batch Location Movement audit record.
    Called from the form button.
    """
    from frappe_wms.wms.events.utils import move_location_qty

    qty = frappe.utils.flt(qty)
    src = frappe.get_doc("Batch Location Stock", source_name)
    move_location_qty(
        item_code=src.item_code,
        batch_no=src.batch_no,
        warehouse=src.warehouse,
        from_location=src.storage_location,
        to_location=to_location,
        qty=qty,
        ref_doctype="Batch Location Stock",
        ref_name=source_name,
    )
    return _("Moved {0} units to {1}.").format(frappe.utils.flt(qty, 3), to_location)


def _get_erpnext_batch_qty(item_code, batch_no, warehouse):
    """
    Get actual batch qty from ERPNext Stock Ledger Entry.

    Handles both:
    - ERPNext <= v15: batch_no stored directly on SLE
    - ERPNext v16:   batch tracked via Serial and Batch Bundle
    """
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM(sle.actual_qty), 0)
        FROM `tabStock Ledger Entry` sle
        WHERE sle.item_code = %(item_code)s
          AND sle.warehouse  = %(warehouse)s
          AND sle.is_cancelled = 0
          AND (
            sle.batch_no = %(batch_no)s
            OR EXISTS (
                SELECT 1 FROM `tabSerial and Batch Entry` sbe
                WHERE sbe.parent   = sle.serial_and_batch_bundle
                  AND sbe.batch_no = %(batch_no)s
            )
          )
        """,
        {"item_code": item_code, "warehouse": warehouse, "batch_no": batch_no},
    )
    return frappe.utils.flt(result[0][0]) if result else 0.0
