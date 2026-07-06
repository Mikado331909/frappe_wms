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
def get_putaway_suggestion(warehouse, batch_no, item_code=None):
    """
    Return the putaway suggestion for a batch in a warehouse.
    Calls the putaway rule engine and returns zone and location.
    """
    frappe.has_permission("Batch Location Stock", "read", throw=True)
    from frappe_wms.wms.events.utils import evaluate_putaway_rule
    customer = frappe.db.get_value("Batch", batch_no, "customer") or None
    return evaluate_putaway_rule(warehouse, customer, item_code)


@frappe.whitelist()
def check_location_compatibility(to_location, batch_no, qty):
    """
    Check whether moving to a location is allowed and return warnings
    so the frontend can show a confirmation dialog.

    Returns a dict:
      status: "ok" | "warning" | "soft_warning" | "blocked"
      type:   "different_customer" | "existing_stock" | "capacity" | null
      message: str
      existing_items: list  (only for status "warning")
      capacity_warning: str | null
    """
    # Discloses which customer's stock sits where - restrict to stock roles.
    frappe.has_permission("Batch Location Stock", "read", throw=True)

    qty = frappe.utils.flt(qty)

    # Customer linked to this batch
    customer = frappe.db.get_value("Batch", batch_no, "customer") or None

    # Location details
    loc = frappe.db.get_value(
        "Storage Location", to_location, ["max_qty", "warehouse"], as_dict=True
    )
    if not loc:
        return {"status": "blocked", "message": _("Location {0} not found.").format(to_location)}

    # Existing stock on this location
    existing_stock = frappe.db.get_all(
        "Batch Location Stock",
        filters={"storage_location": to_location, "qty": [">", 0]},
        fields=["item_code", "batch_no", "qty", "customer", "uom"],
    )

    # Customer-mismatch check
    for row in existing_stock:
        existing_customer = row.customer or None
        if existing_customer != customer:
            return {
                "status": "blocked",
                "type": "different_customer",
                "message": _(
                    "Location {0} already contains stock for {1}. "
                    "Choose another location for {2}."
                ).format(
                    to_location,
                    ("customer " + existing_customer) if existing_customer else "company stock",
                    ("customer " + customer) if customer else "company stock",
                ),
            }

    # Existing stock for the same customer - show an overview for confirmation
    if existing_stock:
        # Group by item_code
        item_summary = {}
        for row in existing_stock:
            key = row.item_code
            if key not in item_summary:
                item_summary[key] = {
                    "item_code": key,
                    "item_name": frappe.db.get_value("Item", key, "item_name") or key,
                    "qty": 0,
                    "uom": row.uom or "",
                }
            item_summary[key]["qty"] = frappe.utils.flt(item_summary[key]["qty"]) + frappe.utils.flt(row.qty)

        # Capacity check
        capacity_warning = None
        if frappe.utils.flt(loc.max_qty) > 0:
            current_total = sum(frappe.utils.flt(r.qty) for r in existing_stock)
            new_total = current_total + qty
            if new_total > frappe.utils.flt(loc.max_qty):
                capacity_warning = _(
                    "Location {0} has a capacity of {1}. "
                    "After placement it will contain {2} ({3}%)."
                ).format(
                    to_location,
                    frappe.utils.flt(loc.max_qty, 3),
                    frappe.utils.flt(new_total, 3),
                    round(new_total / frappe.utils.flt(loc.max_qty) * 100),
                )

        return {
            "status": "warning",
            "type": "existing_stock",
            "message": _("Location {0} already contains stock for {1}:").format(
                to_location,
                ("customer " + customer) if customer else "company stock",
            ),
            "existing_items": list(item_summary.values()),
            "capacity_warning": capacity_warning,
        }

    # No existing stock - capacity check only
    if frappe.utils.flt(loc.max_qty) > 0 and qty > frappe.utils.flt(loc.max_qty):
        return {
            "status": "soft_warning",
            "type": "capacity",
            "message": _(
                "Location {0} has a capacity of {1}. "
                "The quantity ({2}) exceeds the capacity. Continue anyway?"
            ).format(to_location, frappe.utils.flt(loc.max_qty, 3), frappe.utils.flt(qty, 3)),
        }

    return {"status": "ok", "message": ""}


@frappe.whitelist()
def move_stock(source_name, to_location, qty):
    """
    Move qty from one Batch Location Stock record to another location.
    Creates a proper Batch Location Movement audit record.
    Called from the form button.
    """
    from frappe_wms.wms.events.utils import move_location_qty

    frappe.has_permission("Batch Location Stock", "write", throw=True)

    qty = frappe.utils.flt(qty)
    if qty <= 0:
        frappe.throw(_("Quantity must be greater than zero."))
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
