import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, now_datetime


class LocationPick(Document):
    def before_insert(self):
        if not self.posting_date:
            self.posting_date = today()
        if not self.posting_time:
            self.posting_time = now_datetime().strftime("%H:%M:%S")

    def validate(self):
        self._validate_picked_qty()

    def before_submit(self):
        self._check_available_qty()

    def on_submit(self):
        self.status = "Completed"
        self._move_to_staging()
        self._update_pick_list_picked_qty()
        self.db_set("status", "Completed")

    def on_cancel(self):
        self.status = "Cancelled"
        self._reverse_staging()
        self._reverse_pick_list_picked_qty()
        self.db_set("status", "Cancelled")

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_picked_qty(self):
        for line in self.items:
            if not line.picked_qty:
                continue
            if line.picked_qty < 0:
                frappe.throw(
                    _("Row {0}: Picked Qty cannot be negative.").format(line.idx)
                )
            if line.picked_qty > line.required_qty + 0.001:
                frappe.throw(
                    _(
                        "Row {0}: Picked Qty {1} exceeds Required Qty {2} "
                        "for Item {3}."
                    ).format(
                        line.idx,
                        frappe.utils.flt(line.picked_qty, 3),
                        frappe.utils.flt(line.required_qty, 3),
                        line.item_code,
                    )
                )

    def _check_available_qty(self):
        for line in self.items:
            if not line.picked_qty:
                continue
            available = (
                frappe.db.get_value(
                    "Batch Location Stock",
                    {
                        "item_code": line.item_code,
                        "batch_no": line.batch_no,
                        "warehouse": line.warehouse,
                        "storage_location": line.source_location,
                    },
                    "qty",
                )
                or 0.0
            )
            if frappe.utils.flt(available) < line.picked_qty - 0.001:
                frappe.throw(
                    _(
                        "Row {0}: Insufficient qty in {1}. "
                        "Available: {2}, Picked: {3} for Item {4} Batch {5}."
                    ).format(
                        line.idx,
                        line.source_location,
                        frappe.utils.flt(available, 3),
                        frappe.utils.flt(line.picked_qty, 3),
                        line.item_code,
                        line.batch_no,
                    )
                )

    # ------------------------------------------------------------------
    # Submit: move picked qty to Picking Staging
    # ------------------------------------------------------------------

    def _move_to_staging(self):
        from frappe_wms.wms.events.utils import (
            get_picking_staging_location,
            move_location_qty,
        )

        for line in self.items:
            if not line.picked_qty:
                continue
            staging_loc = get_picking_staging_location(line.warehouse)
            move_location_qty(
                item_code=line.item_code,
                batch_no=line.batch_no,
                warehouse=line.warehouse,
                from_location=line.source_location,
                to_location=staging_loc,
                qty=line.picked_qty,
                ref_doctype="Location Pick",
                ref_name=self.name,
            )

    def _update_pick_list_picked_qty(self):
        for line in self.items:
            if not line.pick_list_item or not line.picked_qty:
                continue
            current = (
                frappe.db.get_value(
                    "Pick List Item", line.pick_list_item, "picked_qty"
                )
                or 0.0
            )
            frappe.db.set_value(
                "Pick List Item",
                line.pick_list_item,
                "picked_qty",
                frappe.utils.flt(current) + line.picked_qty,
            )

    # ------------------------------------------------------------------
    # Cancel: reverse staging and pick list
    # ------------------------------------------------------------------

    def _reverse_staging(self):
        from frappe_wms.wms.events.utils import (
            get_picking_staging_location,
            move_location_qty,
        )

        for line in self.items:
            if not line.picked_qty:
                continue
            staging_loc = get_picking_staging_location(line.warehouse)
            move_location_qty(
                item_code=line.item_code,
                batch_no=line.batch_no,
                warehouse=line.warehouse,
                from_location=staging_loc,
                to_location=line.source_location,
                qty=line.picked_qty,
                ref_doctype="Location Pick Cancel",
                ref_name=self.name,
            )

    def _reverse_pick_list_picked_qty(self):
        for line in self.items:
            if not line.pick_list_item or not line.picked_qty:
                continue
            current = (
                frappe.db.get_value(
                    "Pick List Item", line.pick_list_item, "picked_qty"
                )
                or 0.0
            )
            frappe.db.set_value(
                "Pick List Item",
                line.pick_list_item,
                "picked_qty",
                max(0.0, frappe.utils.flt(current) - line.picked_qty),
            )


# ----------------------------------------------------------------------
# Whitelisted API — called from the Pick List client button
# ----------------------------------------------------------------------


@frappe.whitelist()
def generate_location_pick(pick_list):
    """
    Generate a Location Pick from an ERPNext Pick List.

    Allocates available Batch Location Stock (Storage type) sorted by
    pick_sequence to cover each unmet Pick List Item qty.
    """
    pl = frappe.get_doc("Pick List", pick_list)

    doc = frappe.new_doc("Location Pick")
    doc.pick_list = pick_list
    doc.posting_date = today()
    doc.status = "Open"

    for pl_item in pl.locations:
        if not pl_item.batch_no:
            continue

        already_picked = frappe.utils.flt(pl_item.picked_qty)
        required_qty = frappe.utils.flt(pl_item.qty) - already_picked
        if required_qty <= 0.001:
            continue

        available_rows = frappe.db.sql(
            """
            SELECT bls.name, bls.qty, bls.storage_location,
                   sl.pick_sequence
            FROM `tabBatch Location Stock` bls
            INNER JOIN `tabStorage Location` sl ON sl.name = bls.storage_location
            WHERE bls.item_code = %(item_code)s
              AND bls.batch_no   = %(batch_no)s
              AND bls.warehouse  = %(warehouse)s
              AND sl.location_type = 'Storage'
              AND sl.is_active = 1
              AND bls.qty > 0
            ORDER BY sl.pick_sequence ASC, bls.qty DESC
        """,
            {
                "item_code": pl_item.item_code,
                "batch_no": pl_item.batch_no,
                "warehouse": pl_item.warehouse,
            },
            as_dict=True,
        )

        remaining = required_qty
        for avail in available_rows:
            if remaining <= 0.001:
                break
            pick_qty = min(frappe.utils.flt(avail.qty), remaining)
            doc.append(
                "items",
                {
                    "item_code": pl_item.item_code,
                    "batch_no": pl_item.batch_no,
                    "warehouse": pl_item.warehouse,
                    "source_location": avail.storage_location,
                    "required_qty": pick_qty,
                    "picked_qty": 0.0,
                    "uom": pl_item.uom,
                    "pick_list_item": pl_item.name,
                },
            )
            remaining -= pick_qty

    if not doc.items:
        frappe.throw(
            _(
                "No pickable location stock found for Pick List {0}. "
                "Ensure batch items have Storage-type location stock."
            ).format(pick_list)
        )

    doc.insert(ignore_permissions=True)
    return doc.name
