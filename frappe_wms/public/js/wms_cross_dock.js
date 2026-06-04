frappe.ui.form.on('WMS Cross Dock', {
	refresh(frm) {
		if (frm.doc.status === 'Pending') {
			frm.add_custom_button(__('Gereed voor Verzending'), function () {
				frappe.confirm(
					__('Verplaats alle cross-dock items naar Outbound Staging?'),
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
				__('Cross-dock items wachten op XDOCK locatie. Klik "Gereed voor Verzending" om ze naar Outbound Staging te verplaatsen.'),
				'blue'
			);
		} else if (frm.doc.status === 'Staged') {
			frm.set_intro(
				__('Items zijn verplaatst naar Outbound Staging. Maak nu een Delivery Note aan in ERPNext.'),
				'green'
			);
		}
	},
});
