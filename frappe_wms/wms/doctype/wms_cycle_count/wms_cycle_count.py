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
        self.db_set("status", "Cancelled")

    def _calculate_differences(self):
        for line in self.get("count_lines", []):
            if line.counted_qty is not None:
                line.difference = flt(line.counted_qty) - flt(line.system_qty)
                line.status = "Counted"

    def _apply_corrections(self):
        """Past telcorrecties toe op Batch Location Stock."""
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
                # Meer geteld dan in systeem → toevoegen
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
                # Minder geteld dan in systeem → aftrekken
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
                _("{0} locatie(s) gecorrigeerd.").format(corrections_applied),
                indicator="green",
            )


@frappe.whitelist()
def generate_count_lines(cycle_count):
    """
    Genereer telregels vanuit de huidige Batch Location Stock voor de geselecteerde zones.
    Verwijdert eerst bestaande conceptregels.
    """
    doc = frappe.get_doc("WMS Cycle Count", cycle_count)

    zones = [row.zone for row in doc.get("count_zones", [])]
    if not zones:
        frappe.throw(_("Voeg minimaal één zone toe voordat je telregels genereert."))

    # Verwijder bestaande regels
    frappe.db.delete("WMS Cycle Count Line", {"parent": cycle_count})

    # Haal alle BLS-records op voor de geselecteerde zones
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
    doc.save(ignore_permissions=True)
    return lines_added
