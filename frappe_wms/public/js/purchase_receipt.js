// Cross-dock and QC field handlers for Purchase Receipt Item

frappe.ui.form.on('Purchase Receipt Item', {
	wms_cross_dock(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (!row.wms_cross_dock) {
			frappe.model.set_value(cdt, cdn, 'wms_cross_dock_so', null);
			return;
		}
		const customer = row.wms_customer;
		if (!customer) {
			frappe.msgprint({
				title: __('Customer Required'),
				message: __('Fill in the "Customer (WMS)" field before enabling cross-dock.'),
				indicator: 'orange',
			});
			frappe.model.set_value(cdt, cdn, 'wms_cross_dock', 0);
			return;
		}
		_suggest_cross_dock_so(frm, cdt, cdn, customer, row.item_code);
	},
});

function _suggest_cross_dock_so(frm, cdt, cdn, customer, item_code) {
	frappe.call({
		method: 'frappe_wms.wms.events.purchase_receipt.get_open_sales_orders',
		args: { customer, item_code },
		callback(r) {
			const orders = r.message || [];
			if (!orders.length) {
				frappe.msgprint({
					title: __('No Sales Orders'),
					message: __('No open Sales Orders found for customer {0}.', [customer]),
					indicator: 'orange',
				});
				return;
			}
			if (orders.length === 1) {
				frappe.model.set_value(cdt, cdn, 'wms_cross_dock_so', orders[0].name);
				frappe.show_alert({
					message: __('Sales Order {0} filled automatically.', [orders[0].name]),
					indicator: 'green',
				});
				return;
			}
			// Multiple Sales Orders - show a selection dialog
			new frappe.ui.Dialog({
				title: __('Select Sales Order for Cross-dock'),
				fields: [
					{
						label: __('Sales Order'),
						fieldname: 'sales_order',
						fieldtype: 'Link',
						options: 'Sales Order',
						reqd: 1,
						get_query() {
							return {
								filters: {
									customer,
									docstatus: 1,
									status: ['in', ['To Deliver and Bill', 'To Deliver']],
								},
							};
						},
						description: __('Open orders: {0}', [orders.map(o => o.name).join(', ')]),
					},
				],
				primary_action_label: __('Select'),
				primary_action(values) {
					frappe.model.set_value(cdt, cdn, 'wms_cross_dock_so', values.sales_order);
					this.hide();
				},
			}).show();
		},
	});
}
