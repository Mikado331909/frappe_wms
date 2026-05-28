frappe.ui.form.on('Batch Location Stock', {
	refresh(frm) {
		if (frm.doc.__islocal) return;

		frm.add_custom_button(__('Move Stock'), function () {
			let d = new frappe.ui.Dialog({
				title: __('Move Stock to Another Location'),
				fields: [
					{
						label: __('To Location'),
						fieldname: 'to_location',
						fieldtype: 'Link',
						options: 'Storage Location',
						reqd: 1,
						get_query() {
							return {
								filters: {
									warehouse: frm.doc.warehouse,
									is_active: 1,
								},
							};
						},
					},
					{
						label: __('Qty'),
						fieldname: 'qty',
						fieldtype: 'Float',
						reqd: 1,
						default: frm.doc.qty,
					},
				],
				primary_action_label: __('Move'),
				primary_action(values) {
					frappe.call({
						method: 'frappe_wms.wms.doctype.batch_location_stock.batch_location_stock.move_stock',
						args: {
							source_name: frm.doc.name,
							to_location: values.to_location,
							qty: values.qty,
						},
						callback(r) {
							if (!r.exc) {
								frappe.show_alert({ message: r.message, indicator: 'green' });
								frm.reload_doc();
							}
						},
					});
					d.hide();
				},
			});
			d.show();
		});
	},
});
