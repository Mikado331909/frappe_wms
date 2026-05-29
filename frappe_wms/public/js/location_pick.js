frappe.ui.form.on('Location Pick', {
    after_submit: function (frm) {
        // After the Location Pick is submitted, check whether the WMS
        // picked qty differs from what ERPNext has on the Pick List.
        // If so, ask the user whether to overwrite the Pick List value.
        frappe.call({
            method: 'frappe_wms.wms.doctype.location_pick.location_pick.get_pick_qty_discrepancies',
            args: { location_pick: frm.doc.name },
            callback: function (r) {
                if (!r.message || r.message.length === 0) {
                    // No difference – nothing to do
                    return;
                }

                // Build a readable summary of the differences
                let rows = r.message.map(function (d) {
                    return (
                        '<b>' + d.item_code + '</b>: ' +
                        __('Pick List toont') + ' <b>' + d.erpnext_qty + '</b>, ' +
                        __('WMS heeft') + ' <b>' + d.wms_qty + '</b> ' +
                        __('gepickt van') + ' <b>' + d.pl_qty + '</b>'
                    );
                }).join('<br>');

                frappe.confirm(
                    __('Er is een verschil in gepickte aantallen:') +
                    '<br><br>' + rows + '<br><br>' +
                    __('Wil je de Pick List bijwerken met de WMS waarden?'),

                    // YES – overwrite Pick List picked_qty with WMS actuals
                    function () {
                        frappe.call({
                            method: 'frappe_wms.wms.doctype.location_pick.location_pick.apply_pick_qty_update',
                            args: { location_pick: frm.doc.name },
                            callback: function () {
                                frappe.show_alert({
                                    message: __('Pick List picked_qty bijgewerkt naar WMS waarden'),
                                    indicator: 'green',
                                });
                            },
                        });
                    },

                    // NO – leave Pick List as-is
                    function () {
                        frappe.show_alert({
                            message: __('Pick List niet gewijzigd'),
                            indicator: 'blue',
                        });
                    }
                );
            },
        });
    },
});
