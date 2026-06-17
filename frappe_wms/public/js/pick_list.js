frappe.ui.form.on('Pick List', {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frm.add_custom_button(
			__('Generate Location Pick'),
			function () {
				// Haal open Location Picks op om toe te voegen aan
				frappe.call({
					method: 'frappe_wms.wms.doctype.location_pick.location_pick.get_open_location_picks',
					callback(r) {
						const open_picks = r.message || [];

						const fields = [
							{
								label: __('Picking Strategy'),
								fieldname: 'picking_strategy',
								fieldtype: 'Select',
								options: [
									'Pick Sequence',
									'FEFO - First Expired, First Out',
									'FIFO - First In, First Out',
								],
								default: 'Pick Sequence',
								reqd: 1,
								description: __(
									'Pick Sequence: volg de fysieke looproute.<br>'
									+ 'FEFO: batch met vroegste vervaldatum eerst.<br>'
									+ 'FIFO: oudste batch (aanmaakdatum) eerst.'
								),
							},
							{
								label: __('Action'),
								fieldname: 'action',
								fieldtype: 'Select',
								options: [
									'Nieuwe Location Pick aanmaken',
									'Toevoegen aan bestaande Location Pick',
								],
								default: 'Nieuwe Location Pick aanmaken',
								reqd: 1,
							},
							{
								label: __('Existing Location Pick'),
								fieldname: 'existing_location_pick',
								fieldtype: 'Link',
								options: 'Location Pick',
								depends_on: 'eval:doc.action === "Toevoegen aan bestaande Location Pick"',
								mandatory_depends_on: 'eval:doc.action === "Toevoegen aan bestaande Location Pick"',
								get_query() {
									return { filters: { docstatus: 0 } };
								},
								description: open_picks.length
									? __('Open: {0}', [open_picks.map(p => p.name).join(', ')])
									: __('No open Location Picks found.'),
							},
						];

						const d = new frappe.ui.Dialog({
							title: __('Generate Location Pick'),
							fields: fields,
							primary_action_label: __('Generate'),
							primary_action(values) {
								const adding = values.action === 'Toevoegen aan bestaande Location Pick';
								if (adding && !values.existing_location_pick) {
									frappe.msgprint(__('Select an existing Location Pick.'));
									return;
								}
								d.hide();
								frappe.call({
									method: 'frappe_wms.wms.doctype.location_pick.location_pick.generate_location_pick',
									args: {
										pick_lists: JSON.stringify([frm.doc.name]),
										picking_strategy: values.picking_strategy,
										location_pick: adding ? values.existing_location_pick : null,
									},
									freeze: true,
									freeze_message: __('Allocating location stock...'),
									callback(r) {
										if (r.message) {
											frappe.show_alert({
												message: __(
													'Location Pick {0} {1}.',
													[
														`<a href="/app/location-pick/${r.message}">${r.message}</a>`,
														adding ? __('updated') : __('created'),
													]
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
				});
			},
			__('WMS')
		);
	},
});
