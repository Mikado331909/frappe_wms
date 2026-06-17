frappe.ui.form.on('Batch Location Stock', {
	refresh(frm) {
		if (frm.doc.__islocal) return;

		if (frm.doc.qty > 0) {
			frm.add_custom_button(__('Move Stock'), function () {
				_show_move_stock_dialog(frm);
			});
		}
	},
});

function _show_move_stock_dialog(frm) {
	// Haal putaway suggestie op
	frappe.call({
		method: 'frappe_wms.wms.doctype.batch_location_stock.batch_location_stock.get_putaway_suggestion',
		args: {
			warehouse: frm.doc.warehouse,
			batch_no: frm.doc.batch_no,
			item_code: frm.doc.item_code,
		},
		callback(sr) {
			const suggestion = sr.message;
			const suggestion_desc = suggestion
				? __('Recommended: {0} (zone {1}) - {2}', [
					suggestion.location,
					suggestion.zone,
					suggestion.reason,
				  ])
				: __('No putaway suggestion available - choose a location manually.');

			const d = new frappe.ui.Dialog({
				title: __('Move Stock'),
				fields: [
					{
						label: __('To Location'),
						fieldname: 'to_location',
						fieldtype: 'Link',
						options: 'Storage Location',
						reqd: 1,
						default: suggestion ? suggestion.location : '',
						description: suggestion_desc,
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
						label: __('Quantity'),
						fieldname: 'qty',
						fieldtype: 'Float',
						reqd: 1,
						default: frm.doc.qty,
					},
				],
				primary_action_label: __('Move'),
				primary_action(values) {
					if (!values.to_location || !values.qty) return;

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
									title: __('Not Allowed'),
									message: result.message,
									indicator: 'red',
								});
								return;
							}

							if (result.status === 'warning') {
								const items_html = result.existing_items
									.map(i => `<li><b>${i.item_name || i.item_code}</b> (${i.item_code}): `
										+ `${frappe.utils.flt(i.qty, 3)} ${i.uom}</li>`)
									.join('');
								const cap_html = result.capacity_warning
									? `<br><span style="color:orange">&#9888; ${result.capacity_warning}</span>`
									: '';

								frappe.confirm(
									`${result.message}<br><ul>${items_html}</ul>${cap_html}`
									+ `<br>${__('Do you also want to add')} <b>${frm.doc.item_name || frm.doc.item_code}</b> ${__('here?')}`,
									() => _do_move(d, frm, values),
									() => {}
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

							_do_move(d, frm, values);
						},
					});
				},
			});
			d.show();
		},
	});
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
