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
                    // No difference - nothing to do
                    return;
                }

                // Build a readable summary of the differences
                let rows = r.message.map(function (d) {
                    return (
                        '<b>' + d.item_code + '</b>: ' +
                        __('Pick List shows') + ' <b>' + d.erpnext_qty + '</b>, ' +
                        __('WMS has') + ' <b>' + d.wms_qty + '</b> ' +
                        __('picked of') + ' <b>' + d.pl_qty + '</b>'
                    );
                }).join('<br>');

                frappe.confirm(
                    __('There is a difference in picked quantities:') +
                    '<br><br>' + rows + '<br><br>' +
                    __('Do you want to update the Pick List with the WMS values?'),

                    // YES - overwrite Pick List picked_qty with WMS actuals
                    function () {
                        frappe.call({
                            method: 'frappe_wms.wms.doctype.location_pick.location_pick.apply_pick_qty_update',
                            args: { location_pick: frm.doc.name },
                            callback: function () {
                                frappe.show_alert({
                                    message: __('Pick List picked_qty updated to WMS values'),
                                    indicator: 'green',
                                });
                            },
                        });
                    },

                    // NO - leave Pick List as-is
                    function () {
                        frappe.show_alert({
                            message: __('Pick List not changed'),
                            indicator: 'blue',
                        });
                    }
                );
            },
        });
    },
});
