frappe.ui.form.on('Batch Location Stock', {
	refresh(frm) {
		if (frm.doc.__islocal) return;

		if (frm.doc.qty > 0) {
			frm.add_custom_button(__('Voorraad Verplaatsen'), function () {
				_show_move_stock_dialog(frm);
			});
		}
	},
});

function _show_move_stock_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __('Voorraad Verplaatsen'),
		fields: [
			{
				label: __('Naar Locatie'),
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
				label: __('Hoeveelheid'),
				fieldname: 'qty',
				fieldtype: 'Float',
				reqd: 1,
				default: frm.doc.qty,
			},
		],
		primary_action_label: __('Verplaats'),
		primary_action(values) {
			if (!values.to_location || !values.qty) return;

			// Controleer locatie-compatibiliteit voor we verplaatsen
			frappe.call({
				method: 'frappe_wms.wms.doctype.batch_location_stock.batch_location_stock.check_location_compatibility',
				args: {
					to_location: values.to_location,
					batch_no: frm.doc.batch_no,
					qty: values.qty,
				},
				callback(r) {
					const result = r.message;

					if (result.status === 'blocked') {
						frappe.msgprint({
							title: __('Niet toegestaan'),
							message: result.message,
							indicator: 'red',
						});
						return;
					}

					if (result.status === 'warning') {
						// Zelfde klant maar er ligt al iets op de locatie — Ja/Nee dialoog
						const items_html = result.existing_items
							.map(i => `<li><b>${i.item_name}</b> (${i.item_code}): `
								+ `${frappe.utils.flt(i.qty, 3)} ${i.uom}</li>`)
							.join('');

						const capacity_html = result.capacity_warning
							? `<br><span style="color:orange">&#9888; ${result.capacity_warning}</span>`
							: '';

						frappe.confirm(
							`${result.message}<br><ul>${items_html}</ul>${capacity_html}`
							+ `<br>${__('Wil je hier ook')} <b>${frm.doc.item_name || frm.doc.item_code}</b> ${__('toevoegen?')}`,
							() => _do_move(d, frm, values),
							() => { /* Nee — dialoog blijft open */ }
						);
						return;
					}

					if (result.status === 'soft_warning') {
						frappe.confirm(
							result.message,
							() => _do_move(d, frm, values),
							() => {}
						);
						return;
					}

					// Alles ok — direct verplaatsen
					_do_move(d, frm, values);
				},
			});
		},
	});
	d.show();
}

function _do_move(dialog, frm, values) {
	frappe.call({
		method: 'frappe_wms.wms.doctype.batch_location_stock.batch_location_stock.move_stock',
		args: {
			source_name: frm.doc.name,
			to_location: values.to_location,
			qty: values.qty,
		},
		callback(r) {
			if (!r.exc) {
				dialog.hide();
				frappe.show_alert({ message: r.message, indicator: 'green' });
				frm.reload_doc();
			}
		},
	});
}
