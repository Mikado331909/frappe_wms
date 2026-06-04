import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class WmsQcCheck(Document):
    def before_insert(self):
        if not self.check_date:
            self.check_date = today()

    def validate(self):
        self._validate_quantities()

    def on_submit(self):
        self.status = "Completed"
        self._process_qc_results()
        self.db_set("status", "Completed")

    def on_cancel(self):
        # Reverse: approved items back to QC Hold, rejected back from Quarantine
        self._reverse_qc_results()

    # ------------------------------------------------------------------

    def _validate_quantities(self):
        for line in self.items:
            approved = flt(line.approved_qty)
            rejected = flt(line.rejected_qty)
            received = flt(line.received_qty)

            if approved < 0 or rejected < 0:
                frappe.throw(
                    _("Rij {0}: Hoeveelheden mogen niet negatief zijn.").format(line.idx)
                )
            if approved + rejected > received + 0.001:
                frappe.throw(
                    _(
                        "Rij {0}: Goedgekeurd ({1}) + Afgekeurd ({2}) overschrijdt "
                        "ontvangen hoeveelheid ({3})."
                    ).format(line.idx, flt(approved, 3), flt(rejected, 3), flt(received, 3))
                )

            # Auto-bereken outcome
            if approved > 0 and rejected > 0:
                line.outcome = "Gedeeltelijk"
            elif approved > 0:
                line.outcome = "Goedgekeurd"
            elif rejected > 0:
                line.outcome = "Afgekeurd"

    def _process_qc_results(self):
        from frappe_wms.wms.events.utils import (
            get_receiving_location,
            get_quarantine_location,
            move_location_qty,
        )

        for line in self.items:
            approved = flt(line.approved_qty)
            rejected = flt(line.rejected_qty)

            if approved > 0.001:
                # Goedgekeurd: verplaats van QC Hold → RECV (klaar voor putaway)
                recv_loc = get_receiving_location(self.warehouse, raise_if_missing=False)
                if recv_loc and line.from_location:
                    move_location_qty(
                        item_code=line.item_code,
                        batch_no=line.batch_no,
                        warehouse=self.warehouse,
                        from_location=line.from_location,
                        to_location=recv_loc,
                        qty=approved,
                        ref_doctype="WMS QC Check",
                        ref_name=self.name,
                        movement_type="QC Release",
                    )

            if rejected > 0.001:
                # Afgekeurd: verplaats van QC Hold → Quarantine
                quar_loc = get_quarantine_location(self.warehouse, raise_if_missing=False)
                if quar_loc and line.from_location:
                    move_location_qty(
                        item_code=line.item_code,
                        batch_no=line.batch_no,
                        warehouse=self.warehouse,
                        from_location=line.from_location,
                        to_location=quar_loc,
                        qty=rejected,
                        ref_doctype="WMS QC Check",
                        ref_name=self.name,
                        movement_type="QC Release",
                    )

    def _reverse_qc_results(self):
        """Draai QC resultaten terug: approved ← RECV, rejected ← Quarantine → QC Hold."""
        from frappe_wms.wms.events.utils import (
            get_receiving_location,
            get_quarantine_location,
            move_location_qty,
        )

        for line in self.items:
            approved = flt(line.approved_qty)
            rejected = flt(line.rejected_qty)

            if approved > 0.001 and line.from_location:
                recv_loc = get_receiving_location(self.warehouse, raise_if_missing=False)
                if recv_loc:
                    move_location_qty(
                        item_code=line.item_code,
                        batch_no=line.batch_no,
                        warehouse=self.warehouse,
                        from_location=recv_loc,
                        to_location=line.from_location,
                        qty=approved,
                        ref_doctype="WMS QC Check",
                        ref_name=self.name,
                        movement_type="QC Release",
                    )

            if rejected > 0.001 and line.from_location:
                quar_loc = get_quarantine_location(self.warehouse, raise_if_missing=False)
                if quar_loc:
                    move_location_qty(
                        item_code=line.item_code,
                        batch_no=line.batch_no,
                        warehouse=self.warehouse,
                        from_location=quar_loc,
                        to_location=line.from_location,
                        qty=rejected,
                        ref_doctype="WMS QC Check",
                        ref_name=self.name,
                        movement_type="QC Release",
                    )
