import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class WMSCycleCount(Document):
    def before_insert(self):
        if not self.count_date:
            self.count_date = today()

    def validate(self):
        self._calculate_differences()

    def on_submit(self):
        self._apply_corrections()
        self.db_set("status", "Completed")

    def on_cancel(self):
        # Corrections applied at submit mutate real location stock;
        # cancelling the document must reverse them (exact replay).
        from frappe_wms.wms.events.utils import reverse_reference_movements

        reverse_reference_movements("WMS Cycle Count", self.name)
        for line in self.get("count_lines", []):
            if line.status == "Corrected":
                frappe.db.set_value(
                    "WMS Cycle Count Line", line.name, "status", "Counted"
                )
        self.db_set("status", "Cancelled")

    def _calculate_differences(self):
        for line in self.get("count_lines", []):
            if line.counted_qty is not None:
                line.difference = flt(line.counted_qty) - flt(line.system_qty)
                line.status = "Counted"

    def _apply_corrections(self):
        """Apply count corrections to Batch Location Stock."""
        from frappe_wms.wms.events.utils import (
            add_location_qty,
            deduct_location_qty,
        )

        corrections_applied = 0

        for line in self.get("count_lines", []):
            if line.counted_qty is None:
                continue

            diff = flt(line.counted_qty) - flt(line.system_qty)
            if abs(diff) < 0.001:
                continue

            uom = frappe.db.get_value("Item", line.item_code, "stock_uom") or ""

            if diff > 0:
                # Counted more than the system quantity - add stock
                add_location_qty(
                    item_code=line.item_code,
                    batch_no=line.batch_no,
                    warehouse=self.warehouse,
                    storage_location=line.storage_location,
                    qty=diff,
                    uom=uom,
                    ref_doctype="WMS Cycle Count",
                    ref_name=self.name,
                    movement_type="Cycle Count",
                )
            else:
                # Counted less than the system quantity - deduct stock
                deduct_location_qty(
                    item_code=line.item_code,
                    batch_no=line.batch_no,
                    warehouse=self.warehouse,
                    storage_location=line.storage_location,
                    qty=abs(diff),
                    ref_doctype="WMS Cycle Count",
                    ref_name=self.name,
                    movement_type="Cycle Count",
                )

            frappe.db.set_value("WMS Cycle Count Line", line.name, "status", "Corrected")
            corrections_applied += 1

        if corrections_applied:
            frappe.msgprint(
                _(
                    "{0} location(s) corrected. Note: these corrections only "
                    "adjust WMS location stock. If the counted differences "
                    "are real physical gains or losses, create an ERPNext "
                    "Stock Reconciliation as well, otherwise WMS and the "
                    "ERPNext stock ledger will disagree."
                ).format(corrections_applied),
                indicator="orange",
            )


@frappe.whitelist()
def generate_count_lines(cycle_count):
    """
    Generate count lines from current Batch Location Stock for the selected zones.
    Deletes existing draft lines first.
    """
    frappe.has_permission("WMS Cycle Count", "write", throw=True)
    doc = frappe.get_doc("WMS Cycle Count", cycle_count)

    if doc.docstatus != 0:
        frappe.throw(_("Count lines can only be regenerated on a draft Cycle Count."))

    zones = [row.zone for row in doc.get("count_zones", [])]
    if not zones:
        frappe.throw(_("Add at least one zone before generating count lines."))

    # Clear existing lines through the document API so the in-memory child
    # table and the database stay consistent (frappe.db.delete + append on a
    # stale doc leaves phantom rows in memory).
    doc.set("count_lines", [])

    # Load all BLS records for the selected zones
    bls_records = frappe.db.sql(
        """
        SELECT
            bls.storage_location, bls.zone, bls.item_code, bls.batch_no,
            bls.customer, bls.qty AS system_qty, i.item_name
        FROM `tabBatch Location Stock` bls
        LEFT JOIN `tabItem` i ON i.name = bls.item_code
        WHERE bls.zone IN %(zones)s
          AND bls.warehouse = %(warehouse)s
        ORDER BY bls.storage_location ASC, bls.item_code ASC
        """,
        {"zones": tuple(zones), "warehouse": doc.warehouse},
        as_dict=True,
    )

    lines_added = 0
    for rec in bls_records:
        doc.append(
            "count_lines",
            {
                "storage_location": rec.storage_location,
                "zone": rec.zone or "",
                "item_code": rec.item_code,
                "item_name": rec.item_name or "",
                "batch_no": rec.batch_no,
                "customer": rec.customer,
                "system_qty": flt(rec.system_qty, 3),
                "counted_qty": None,
                "difference": None,
                "status": "Pending",
            },
        )
        lines_added += 1

    doc.status = "In Progress"
    doc.save()
    return lines_added
