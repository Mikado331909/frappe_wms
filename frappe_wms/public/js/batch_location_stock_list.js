frappe.listview_settings['Batch Location Stock'] = {
	filters: [['qty', '>', 0]],

	get_indicator(doc) {
		if (doc.qty <= 0) {
			return [__('Empty'), 'grey', 'qty,<=,0'];
		} else if (doc.qty <= 2) {
			return [__('Low'), 'orange', 'qty,>,0|qty,<=,2'];
		}
		return [__('In Stock'), 'green', 'qty,>,0'];
	},
};
