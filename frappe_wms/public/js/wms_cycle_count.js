frappe.ui.form.on('WMS Cycle Count', {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;

		const has_lines = frm.doc.count_lines && frm.doc.count_lines.length > 0;

		if (!has_lines) {
			frm.add_custom_button(__('Telregels Genereren'), function () {
				if (!frm.doc.count_zones || !frm.doc.count_zones.length) {
					frappe.msgprint({
						title: __('Geen zones'),
						message: __('Voeg minimaal één zone toe voordat je telregels genereert.'),
						indicator: 'orange',
					});
					return;
				}
				frappe.call({
					method: 'frappe_wms.wms.doctype.wms_cycle_count.wms_cycle_count.generate_count_lines',
					args: { cycle_count: frm.doc.name },
					freeze: true,
					freeze_message: __('Telregels genereren...'),
					callback(r) {
						frm.reload_doc();
						frappe.show_alert({
							message: __('<b>{0}</b> telregels aangemaakt.', [r.message || 0]),
							indicator: 'green',
						});
					},
				});
			}).addClass('btn-primary');
		}

		if (has_lines) {
			frm.set_intro(
				__('Vul de getelde hoeveelheden in per regel. Bij indienen worden afwijkingen automatisch gecorrigeerd in de WMS voorraad.'),
				'blue'
			);
		}
	},

	validate(frm) {
		// Bereken verschillen live zodat medewerker ze ziet tijdens invullen
		(frm.doc.count_lines || []).forEach(line => {
			if (line.counted_qty !== null && line.counted_qty !== undefined) {
				const diff = frappe.utils.flt(line.counted_qty) - frappe.utils.flt(line.system_qty);
				frappe.model.set_value(line.doctype, line.name, 'difference', diff);
			}
		});
	},
});
