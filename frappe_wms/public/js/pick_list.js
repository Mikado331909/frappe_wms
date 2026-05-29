frappe.ui.form.on('Pick List', {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frm.add_custom_button(
			__('Generate Location Pick'),
			function () {
				let d = new frappe.ui.Dialog({
					title: __('Generate Location Pick'),
					fields: [
						{
							label: __('Picking Strategy'),
							fieldname: 'picking_strategy',
							fieldtype: 'Select',
							options: [
								'Pick Sequence',
								'FEFO – First Expired, First Out',
								'FIFO – First In, First Out',
							],
							default: 'Pick Sequence',
							reqd: 1,
							description: __(
								'Pick Sequence: follow warehouse location order.<br>'
								+ 'FEFO: pick batches closest to expiry first.<br>'
								+ 'FIFO: pick oldest batches (by creation date) first.'
							),
						},
					],
					primary_action_label: __('Generate'),
					primary_action(values) {
						d.hide();
						frappe.call({
							method: 'frappe_wms.wms.doctype.location_pick.location_pick.generate_location_pick',
							args: {
								pick_list: frm.doc.name,
								picking_strategy: values.picking_strategy,
							},
							freeze: true,
							freeze_message: __('Allocating location stock…'),
							callback(r) {
								if (r.message) {
									frappe.show_alert({
										message: __(
											'Location Pick {0} created.',
											[`<a href="/app/location-pick/${r.message}">${r.message}</a>`]
										),
										indicator: 'green',
									});
									frappe.set_route('Form', 'Location Pick', r.message);
								}
							},
						});
					},
				});
				d.show();
			},
			__('WMS')
		);
	},
});
