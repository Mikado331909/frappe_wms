import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class WMSCrossDock(Document):
    def before_insert(self):
        if not self.posting_date:
            self.posting_date = today()

    @frappe.whitelist()
    def mark_ready_to_ship(self):
        """
        Move all cross-dock items from the XDOCK location to Outbound Staging.
        Called from the form button.
        """
        from frappe_wms.wms.events.utils import (
            get_picking_staging_location,
            move_location_qty,
        )

        self.check_permission("write")

        moved = 0
        for item in self.items:
            if not item.xdock_location:
                continue

            # Re-read staged_qty under a row lock. Two concurrent clicks on
            # the button would otherwise both see the in-memory staged_qty,
            # both compute the full remaining qty, and move the stock twice
            # while recording it once (lost update).
            locked = frappe.db.sql(
                """
                SELECT staged_qty FROM `tabWMS Cross Dock Item`
                WHERE name = %s FOR UPDATE
                """,
                item.name,
                as_dict=True,
            )
            current_staged = flt(locked[0].staged_qty) if locked else flt(item.staged_qty)

            qty_remaining = flt(item.qty) - current_staged
            if qty_remaining <= 0.001:
                continue

            # Check available stock on the XDOCK location
            available = (
                frappe.db.get_value(
                    "Batch Location Stock",
                    {
                        "item_code": item.item_code,
                        "batch_no": item.batch_no,
                        "warehouse": item.warehouse,
                        "storage_location": item.xdock_location,
                    },
                    "qty",
                )
                or 0.0
            )
            qty_to_move = min(qty_remaining, flt(available))
            if qty_to_move <= 0.001:
                continue

            staging_loc = get_picking_staging_location(item.warehouse, raise_if_missing=False)
            if not staging_loc:
                continue

            move_location_qty(
                item_code=item.item_code,
                batch_no=item.batch_no,
                warehouse=item.warehouse,
                from_location=item.xdock_location,
                to_location=staging_loc,
                qty=qty_to_move,
                ref_doctype="WMS Cross Dock",
                ref_name=self.name,
                movement_type="Cross-dock",
            )

            frappe.db.set_value(
                "WMS Cross Dock Item",
                item.name,
                "staged_qty",
                current_staged + qty_to_move,
            )
            moved += qty_to_move

        if moved > 0:
            self.db_set("status", "Staged")
            frappe.msgprint(
                _("{0} units moved to Outbound Staging.").format(flt(moved, 3)),
                indicator="green",
            )
        else:
            frappe.msgprint(
                _("No stock found on the cross-dock locations."),
                indicator="orange",
            )
