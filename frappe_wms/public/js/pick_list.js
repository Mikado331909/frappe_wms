frappe.ui.form.on('Pick List', {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frm.add_custom_button(
			__('Generate Location Pick'),
			function () {
				frappe.confirm(
					__(
						'Generate a Location Pick for <strong>{0}</strong>?<br>'
						+ 'Lines will be allocated from Storage locations sorted by pick sequence.',
						[frm.doc.name]
					),
					function () {
						frappe.call({
							method:
								'frappe_wms.wms.doctype.location_pick.location_pick.generate_location_pick',
							args: { pick_list: frm.doc.name },
							freeze: true,
							freeze_message: __('Allocating location stock…'),
							callback(r) {
								if (r.message) {
									frappe.show_alert({
										message: __('Location Pick {0} created.', [
											`<a href="/app/location-pick/${r.message}">${r.message}</a>`,
										]),
										indicator: 'green',
									});
									frappe.set_route('Form', 'Location Pick', r.message);
								}
							},
						});
					}
				);
			},
			__('WMS')
		);
	},
});
