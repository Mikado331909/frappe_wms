import frappe
from frappe import _
from frappe.utils import today
from frappe_wms.wms.events.utils import (
    iter_batch_entries,
    get_receiving_location,
    get_qc_hold_location,
    get_cross_dock_location,
    add_location_qty,
    deduct_location_qty,
)


def _set_customer_on_batch(batch_no, customer):
    """Schrijf de klant naar het Batch record als die er nog niet op staat."""
    if not batch_no or not customer:
        return
    existing = frappe.db.get_value("Batch", batch_no, "customer")
    if not existing:
        frappe.db.set_value("Batch", batch_no, "customer", customer)


def _get_cross_dock_so(item):
    """
    Geeft de gekoppelde Sales Order voor cross-dock terug, of None.
    Controleert:
    1. Handmatige vlag wms_cross_dock + wms_cross_dock_so
    2. Auto-detectie via PO Detail → Sales Order koppeling
    """
    if item.get("wms_cross_dock"):
        so = item.get("wms_cross_dock_so") or None
        return so if so else True  # True = cross-dock maar geen SO opgegeven

    # Auto-detectie: Purchase Order Item → Sales Order
    if item.get("sales_order"):
        return item.sales_order

    po_item = item.get("purchase_order_item") or item.get("po_detail")
    if po_item:
        so = frappe.db.get_value("Purchase Order Item", po_item, "sales_order")
        if so:
            return so

    return None


def _create_qc_check(doc, qc_items):
    """Maak een WMS QC Check document aan voor de opgegeven items."""
    # Groepeer op warehouse
    by_warehouse = {}
    for item in qc_items:
        wh = item["warehouse"]
        by_warehouse.setdefault(wh, []).append(item)

    for warehouse, items in by_warehouse.items():
        qc = frappe.get_doc({
            "doctype": "WMS QC Check",
            "purchase_receipt": doc.name,
            "warehouse": warehouse,
            "check_type": "Beide",
            "status": "Pending",
            "check_date": today(),
            "items": [
                {
                    "item_code": it["item_code"],
                    "batch_no": it["batch_no"],
                    "from_location": it["qc_location"],
                    "received_qty": it["received_qty"],
                    "approved_qty": 0,
                    "rejected_qty": 0,
                }
                for it in items
            ],
        })
        qc.flags.ignore_permissions = True
        qc.insert()
        frappe.msgprint(
            _("WMS QC Check {0} aangemaakt voor warehouse {1}.").format(
                f'<a href="/app/wms-qc-check/{qc.name}">{qc.name}</a>', warehouse
            ),
            title=_("QC Vereist"),
            indicator="orange",
        )


def _create_cross_dock(doc, xdock_items):
    """Maak een WMS Cross Dock document aan voor de opgegeven items."""
    # Groepeer op klant
    by_customer = {}
    for item in xdock_items:
        cust = item.get("customer") or ""
        by_customer.setdefault(cust, []).append(item)

    for customer, items in by_customer.items():
        xd = frappe.get_doc({
            "doctype": "WMS Cross Dock",
            "purchase_receipt": doc.name,
            "customer": customer or None,
            "status": "Pending",
            "posting_date": today(),
            "items": [
                {
                    "item_code": it["item_code"],
                    "batch_no": it["batch_no"],
                    "warehouse": it["warehouse"],
                    "xdock_location": it["xdock_location"],
                    "sales_order": it["sales_order"] if isinstance(it["sales_order"], str) else None,
                    "qty": it["qty"],
                    "uom": it.get("uom"),
                    "staged_qty": 0,
                    "delivered_qty": 0,
                }
                for it in items
            ],
        })
        xd.flags.ignore_permissions = True
        xd.insert()
        frappe.msgprint(
            _("WMS Cross Dock {0} aangemaakt.").format(
                f'<a href="/app/wms-cross-dock/{xd.name}">{xd.name}</a>'
            ),
            title=_("Cross-dock"),
            indicator="blue",
        )


def on_submit(doc, method=None):
    if not frappe.db.get_single_value("WMS Settings", "auto_create_on_receipt"):
        return

    qc_items = []
    xdock_items = []

    for item in doc.items:
        warehouse = item.warehouse or doc.set_warehouse
        if not warehouse:
            continue

        customer = item.get("wms_customer") or None
        require_qc = item.get("wms_require_qc") or 0
        cross_dock_so = _get_cross_dock_so(item)

        for batch_no, qty in iter_batch_entries(item):
            _set_customer_on_batch(batch_no, customer)

            if cross_dock_so:
                # Cross-dock: stuur naar XDOCK locatie
                xdock_loc = get_cross_dock_location(warehouse, raise_if_missing=False)
                if xdock_loc:
                    add_location_qty(
                        item_code=item.item_code,
                        batch_no=batch_no,
                        warehouse=warehouse,
                        storage_location=xdock_loc,
                        qty=qty,
                        uom=item.uom,
                        ref_doctype="Purchase Receipt",
                        ref_name=doc.name,
                        movement_type="Cross-dock",
                    )
                    xdock_items.append({
                        "item_code": item.item_code,
                        "batch_no": batch_no,
                        "warehouse": warehouse,
                        "xdock_location": xdock_loc,
                        "sales_order": cross_dock_so if isinstance(cross_dock_so, str) else None,
                        "qty": qty,
                        "uom": item.uom,
                        "customer": customer,
                    })
                    continue

            if require_qc:
                # QC vereist: stuur naar QC Hold locatie
                qc_loc = get_qc_hold_location(warehouse, raise_if_missing=False)
                if qc_loc:
                    add_location_qty(
                        item_code=item.item_code,
                        batch_no=batch_no,
                        warehouse=warehouse,
                        storage_location=qc_loc,
                        qty=qty,
                        uom=item.uom,
                        ref_doctype="Purchase Receipt",
                        ref_name=doc.name,
                        movement_type="Inbound",
                    )
                    qc_items.append({
                        "item_code": item.item_code,
                        "batch_no": batch_no,
                        "warehouse": warehouse,
                        "qc_location": qc_loc,
                        "received_qty": qty,
                        "uom": item.uom,
                    })
                    continue

            # Normaal: naar RECV
            receiving_loc = get_receiving_location(warehouse, raise_if_missing=False)
            if not receiving_loc:
                continue
            add_location_qty(
                item_code=item.item_code,
                batch_no=batch_no,
                warehouse=warehouse,
                storage_location=receiving_loc,
                qty=qty,
                uom=item.uom,
                ref_doctype="Purchase Receipt",
                ref_name=doc.name,
                movement_type="Inbound",
            )

    if qc_items:
        _create_qc_check(doc, qc_items)

    if xdock_items:
        _create_cross_dock(doc, xdock_items)


def on_cancel(doc, method=None):
    if not frappe.db.get_single_value("WMS Settings", "auto_create_on_receipt"):
        return

    for item in doc.items:
        warehouse = item.warehouse or doc.set_warehouse
        if not warehouse:
            continue

        require_qc = item.get("wms_require_qc") or 0
        cross_dock_so = _get_cross_dock_so(item)

        # Bepaal de locatie waar items geplaatst zijn
        if cross_dock_so:
            loc = get_cross_dock_location(warehouse, raise_if_missing=False)
        elif require_qc:
            loc = get_qc_hold_location(warehouse, raise_if_missing=False)
        else:
            loc = get_receiving_location(warehouse, raise_if_missing=False)

        if not loc:
            continue

        for batch_no, qty in iter_batch_entries(item):
            # Controleer hoeveel er nog op de verwachte locatie staat
            available = (
                frappe.db.get_value(
                    "Batch Location Stock",
                    {
                        "item_code": item.item_code,
                        "batch_no": batch_no,
                        "warehouse": warehouse,
                        "storage_location": loc,
                    },
                    "qty",
                )
                or 0.0
            )
            deduct_qty = min(qty, available)
            if deduct_qty <= 0.001:
                continue

            deduct_location_qty(
                item_code=item.item_code,
                batch_no=batch_no,
                warehouse=warehouse,
                storage_location=loc,
                qty=deduct_qty,
                ref_doctype="Purchase Receipt Cancel",
                ref_name=doc.name,
                movement_type="Inbound",
            )


@frappe.whitelist()
def get_open_sales_orders(customer, item_code=None):
    """Geef open Sales Orders terug voor een klant (optioneel gefilterd op artikel)."""
    filters = {
        "customer": customer,
        "docstatus": 1,
        "status": ["in", ["To Deliver and Bill", "To Deliver", "To Bill"]],
    }

    if item_code:
        so_names_raw = frappe.db.sql(
            "SELECT DISTINCT parent FROM `tabSales Order Item` WHERE item_code = %s",
            item_code,
        )
        so_list = [r[0] for r in so_names_raw]
        if not so_list:
            return []
        filters["name"] = ["in", so_list]

    return frappe.get_all(
        "Sales Order",
        filters=filters,
        fields=["name", "customer", "transaction_date", "delivery_date"],
        order_by="delivery_date asc",
        limit=10,
    )
