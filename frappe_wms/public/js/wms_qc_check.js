frappe.ui.form.on('WMS QC Check', {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.set_intro(
				__('QC Check afgerond. Goedgekeurde items zijn verplaatst naar RECV, afgekeurde naar Quarantine.'),
				'green'
			);
			return;
		}

		if (frm.doc.docstatus === 0) {
			if (frm.doc.status === 'Pending') {
				frm.add_custom_button(__('Starten'), function () {
					frappe.call({
						method: 'frappe.client.set_value',
						args: {
							doctype: 'WMS QC Check',
							name: frm.doc.name,
							fieldname: { status: 'In Progress', inspector: frappe.session.user },
						},
						callback() { frm.reload_doc(); },
					});
				}).addClass('btn-primary');
			}

			frm.set_intro(
				__('Vul per regel de goedgekeurde en afgekeurde hoeveelheden in. '
				   + 'Bij indienen worden goedgekeurde items naar RECV en afgekeurde naar Quarantine verplaatst.'),
				'blue'
			);
		}
	},

	validate(frm) {
		// Auto-bereken afgekeurde hoeveelheid als leeg
		frm.doc.items.forEach(line => {
			const approved = frappe.utils.flt(line.approved_qty);
			const received = frappe.utils.flt(line.received_qty);
			if (line.rejected_qty === null || line.rejected_qty === undefined || line.rejected_qty === '') {
				frappe.model.set_value(line.doctype, line.name, 'rejected_qty', received - approved);
			}
		});
	},
});
