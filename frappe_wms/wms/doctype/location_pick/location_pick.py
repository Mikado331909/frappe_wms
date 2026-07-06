import json
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
        self._validate_no_duplicate_pick_lists()

    def before_submit(self):
        self._check_available_qty()

    def on_submit(self):
        self._move_to_staging()
        self.db_set("status", "Completed")

    def on_cancel(self):
        self._reverse_staging()
        self.db_set("status", "Cancelled")

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_no_duplicate_pick_lists(self):
        seen = set()
        for row in self.get("pick_lists", []):
            if row.pick_list in seen:
                frappe.throw(
                    _("Pick List {0} was added more than once.").format(row.pick_list)
                )
            seen.add(row.pick_list)

    def _validate_picked_qty(self):
        for line in self.items:
            if not line.picked_qty:
                continue
            if line.picked_qty < 0:
                frappe.throw(
                    _("Row {0}: Picked quantity cannot be negative.").format(line.idx)
                )
            if line.picked_qty > line.required_qty + 0.001:
                frappe.throw(
                    _(
                        "Row {0}: Picked quantity {1} exceeds "
                        "required quantity {2} for item {3}."
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
                        "Row {0}: Insufficient stock on {1}. "
                        "Available: {2}, Picked: {3} for item {4} batch {5}."
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

    # ------------------------------------------------------------------
    # Cancel: reverse staging back to source locations
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
                ref_doctype="Location Pick",
                ref_name=self.name,
            )


# ----------------------------------------------------------------------
# Whitelisted API - called from the Pick List client button
# ----------------------------------------------------------------------


@frappe.whitelist()
def get_open_location_picks():
    """Return open, not submitted Location Pick documents."""
    frappe.has_permission("Location Pick", "read", throw=True)
    return frappe.get_all(
        "Location Pick",
        filters={"docstatus": 0},
        fields=["name", "posting_date"],
        order_by="posting_date desc",
        limit=20,
    )


@frappe.whitelist()
def generate_location_pick(pick_lists, picking_strategy=None, location_pick=None):
    """
    Generate or extend a Location Pick from one or more ERPNext Pick Lists.

    pick_lists:       JSON list of Pick List names, or a single name as a string
    picking_strategy: 'Pick Sequence' / 'FEFO ...' / 'FIFO ...'
    location_pick:    if given, append lines to this existing Location Pick
    """
    frappe.has_permission("Location Pick", "create", throw=True)
    frappe.has_permission("Pick List", "read", throw=True)

    # Normalize to a Python list
    if isinstance(pick_lists, str):
        try:
            pick_lists = json.loads(pick_lists)
        except (json.JSONDecodeError, ValueError):
            pick_lists = [pick_lists]

    if not picking_strategy:
        picking_strategy = "Pick Sequence"

    order_by = _order_by_for_strategy(picking_strategy)

    # Load an existing Location Pick or create a new one
    if location_pick:
        doc = frappe.get_doc("Location Pick", location_pick)
        if doc.docstatus != 0:
            frappe.throw(
                _("Location Pick {0} is already submitted and cannot be changed.").format(
                    location_pick
                )
            )
    else:
        doc = frappe.new_doc("Location Pick")
        doc.picking_strategy = picking_strategy
        doc.posting_date = today()
        doc.status = "Open"

    # Pick Lists already linked to this document
    existing_pick_lists = {row.pick_list for row in doc.get("pick_lists", [])}
    new_lines_added = 0

    for pl_name in pick_lists:
        if pl_name in existing_pick_lists:
            frappe.msgprint(
                _("Pick List {0} is already added to this Location Pick.").format(pl_name)
            )
            continue

        # Lock the Pick List row so two users generating a Location Pick for
        # the same Pick List at the same time cannot both read the same
        # "already committed" totals and double-plan the stock.
        frappe.db.sql(
            "SELECT name FROM `tabPick List` WHERE name = %s FOR UPDATE",
            pl_name,
        )

        pl = frappe.get_doc("Pick List", pl_name)
        doc.append("pick_lists", {"pick_list": pl_name})

        for pl_item in pl.locations:
            for batch_no, batch_qty in _iter_pl_item_batch_entries(pl_item):
                batch_qty = frappe.utils.flt(batch_qty)
                if not batch_no or batch_qty <= 0:
                    continue

                # Qty already committed by other non-cancelled Location Picks
                # for this exact Pick List row and batch.
                wms_committed = frappe.utils.flt(
                    frappe.db.sql("""
                        SELECT COALESCE(SUM(lpl.required_qty), 0)
                        FROM `tabLocation Pick Line` lpl
                        INNER JOIN `tabLocation Pick` lp ON lp.name = lpl.parent
                        WHERE lpl.pick_list_item = %s
                          AND lpl.batch_no = %s
                          AND lp.docstatus IN (0, 1)
                    """, (pl_item.name, batch_no))[0][0]
                )
                required_qty = batch_qty - wms_committed
                if required_qty <= 0.001:
                    continue

                # Available storage locations for this item, batch and warehouse.
                # Supports both old ('Storage') and new ('Active Storage') location types.
                available_rows = frappe.db.sql(
                    f"""
                    SELECT bls.name, bls.qty, bls.storage_location,
                           sl.pick_sequence,
                           b.expiry_date, b.creation AS batch_creation
                    FROM `tabBatch Location Stock` bls
                    INNER JOIN `tabStorage Location` sl ON sl.name = bls.storage_location
                    LEFT  JOIN `tabBatch`            b  ON b.name  = bls.batch_no
                    WHERE bls.item_code = %(item_code)s
                      AND bls.batch_no   = %(batch_no)s
                      AND bls.warehouse  = %(warehouse)s
                      AND sl.location_type IN ('Storage', 'Active Storage')
                      AND sl.is_active = 1
                      AND bls.qty > 0
                    ORDER BY {order_by}
                    """,
                    {
                        "item_code": pl_item.item_code,
                        "batch_no": batch_no,
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
                            "batch_no": batch_no,
                            "warehouse": pl_item.warehouse,
                            "source_location": avail.storage_location,
                            "required_qty": pick_qty,
                            "picked_qty": 0.0,
                            "uom": pl_item.uom,
                            "pick_list_item": pl_item.name,
                            "pick_list": pl_name,
                        },
                    )
                    new_lines_added += 1
                    remaining -= pick_qty

    if not doc.items and not location_pick:
        frappe.throw(
            _("No pickable location stock found for the given Pick Lists.")
        )

    if new_lines_added == 0 and location_pick:
        frappe.throw(
            _(
                "No new lines added - all items are already planned "
                "or there is no stock on storage locations."
            )
        )

    if location_pick:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)

    return doc.name


# ----------------------------------------------------------------------
# Whitelisted API - called from location_pick.js after submit
# ----------------------------------------------------------------------


@frappe.whitelist()
def get_pick_qty_discrepancies(location_pick):
    """Compare WMS picked qty with ERPNext Pick List picked_qty per line."""
    frappe.has_permission("Location Pick", "read", throw=True)
    doc = frappe.get_doc("Location Pick", location_pick)
    discrepancies = []

    seen_pl_items = set()
    for line in doc.items:
        if not line.pick_list_item or line.pick_list_item in seen_pl_items:
            continue
        seen_pl_items.add(line.pick_list_item)

        wms_qty = frappe.utils.flt(
            frappe.db.sql("""
                SELECT COALESCE(SUM(lpl.picked_qty), 0)
                FROM `tabLocation Pick Line` lpl
                INNER JOIN `tabLocation Pick` lp ON lp.name = lpl.parent
                WHERE lpl.pick_list_item = %s AND lp.docstatus = 1
            """, line.pick_list_item)[0][0]
        )
        erpnext_qty = frappe.utils.flt(
            frappe.db.get_value("Pick List Item", line.pick_list_item, "picked_qty") or 0
        )
        pl_qty = frappe.utils.flt(
            frappe.db.get_value("Pick List Item", line.pick_list_item, "qty") or 0
        )

        if abs(wms_qty - erpnext_qty) > 0.001:
            discrepancies.append({
                "item_code": line.item_code,
                "pick_list": line.pick_list,
                "pick_list_item": line.pick_list_item,
                "wms_qty": wms_qty,
                "erpnext_qty": erpnext_qty,
                "pl_qty": pl_qty,
            })

    return discrepancies


@frappe.whitelist()
def apply_pick_qty_update(location_pick):
    """Overwrite Pick List Item.picked_qty with the actual WMS quantities."""
    # Writes into ERPNext Pick List rows, so require write permission there.
    frappe.has_permission("Pick List", "write", throw=True)
    doc = frappe.get_doc("Location Pick", location_pick)

    seen_pl_items = set()
    for line in doc.items:
        if not line.pick_list_item or line.pick_list_item in seen_pl_items:
            continue
        seen_pl_items.add(line.pick_list_item)

        wms_qty = frappe.utils.flt(
            frappe.db.sql("""
                SELECT COALESCE(SUM(lpl.picked_qty), 0)
                FROM `tabLocation Pick Line` lpl
                INNER JOIN `tabLocation Pick` lp ON lp.name = lpl.parent
                WHERE lpl.pick_list_item = %s AND lp.docstatus = 1
            """, line.pick_list_item)[0][0]
        )
        frappe.db.set_value("Pick List Item", line.pick_list_item, "picked_qty", wms_qty)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _iter_pl_item_batch_entries(pl_item):
    """Yield batch and qty pairs for a Pick List Item row."""
    if getattr(pl_item, "batch_no", None):
        # Yield in stock UOM, consistent with Serial and Batch Entry rows.
        stock_qty = frappe.utils.flt(getattr(pl_item, "stock_qty", 0))
        if not stock_qty:
            stock_qty = frappe.utils.flt(getattr(pl_item, "qty", 0)) * (
                frappe.utils.flt(getattr(pl_item, "conversion_factor", 0)) or 1.0
            )
        yield pl_item.batch_no, stock_qty
        return

    bundle = getattr(pl_item, "serial_and_batch_bundle", None)
    if not bundle and getattr(pl_item, "name", None):
        bundle = frappe.db.get_value(
            "Pick List Item", pl_item.name, "serial_and_batch_bundle"
        )

    if bundle:
        entries = frappe.db.get_all(
            "Serial and Batch Entry",
            filters={"parent": bundle},
            fields=["batch_no", "qty"],
        )
        for entry in entries:
            if entry.batch_no and frappe.utils.flt(entry.qty) != 0:
                yield entry.batch_no, abs(frappe.utils.flt(entry.qty))


def _get_pl_item_batch_no(pl_item):
    """Return the first batch number for legacy callers."""
    for batch_no, _qty in _iter_pl_item_batch_entries(pl_item):
        return batch_no
    return None


def _order_by_for_strategy(strategy):
    """Return the SQL ORDER BY clause for the chosen picking strategy."""
    if "FEFO" in strategy:
        return (
            "CASE WHEN b.expiry_date IS NULL THEN '9999-12-31' "
            "     ELSE b.expiry_date END ASC, "
            "sl.pick_sequence ASC"
        )
    if "FIFO" in strategy:
        return "b.creation ASC, sl.pick_sequence ASC"
    return "sl.pick_sequence ASC, bls.qty DESC"
