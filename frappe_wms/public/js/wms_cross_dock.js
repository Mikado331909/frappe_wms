frappe.ui.form.on('WMS Cross Dock', {
	refresh(frm) {
		if (frm.doc.status === 'Pending') {
			frm.add_custom_button(__('Ready to Ship'), function () {
				frappe.confirm(
					__('Move all cross-dock items to Outbound Staging?'),
					function () {
						frappe.call({
							method: 'frappe_wms.wms.doctype.wms_cross_dock.wms_cross_dock.WmsCrossDock.mark_ready_to_ship',
							args: { doc: frm.doc },
							callback() { frm.reload_doc(); },
						});
					}
				);
			}).addClass('btn-primary');

			frm.set_intro(
				__('Cross-dock items are waiting on the XDOCK location. Click "Ready to Ship" to move them to Outbound Staging.'),
				'blue'
			);
		} else if (frm.doc.status === 'Staged') {
			frm.set_intro(
				__('Items were moved to Outbound Staging. Create a Delivery Note in ERPNext next.'),
				'green'
			);
		}
	},
});
