// Cross-dock en QC veld handlers voor Purchase Receipt Item

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
				title: __('Klant vereist'),
				message: __('Vul eerst het veld "Customer (WMS)" in voordat je cross-dock activeert.'),
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
					title: __('Geen Sales Orders'),
					message: __('Geen open Sales Orders gevonden voor klant {0}.', [customer]),
					indicator: 'orange',
				});
				return;
			}
			if (orders.length === 1) {
				frappe.model.set_value(cdt, cdn, 'wms_cross_dock_so', orders[0].name);
				frappe.show_alert({
					message: __('Sales Order {0} automatisch ingevuld.', [orders[0].name]),
					indicator: 'green',
				});
				return;
			}
			// Meerdere SOs — toon keuzedialoog
			new frappe.ui.Dialog({
				title: __('Selecteer Sales Order voor Cross-dock'),
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
				primary_action_label: __('Selecteren'),
				primary_action(values) {
					frappe.model.set_value(cdt, cdn, 'wms_cross_dock_so', values.sales_order);
					this.hide();
				},
			}).show();
		},
	});
}
