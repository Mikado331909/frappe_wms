import frappe
from frappe import _
from frappe.model.document import Document


class WmsZone(Document):
    def validate(self):
        self._validate_dedicated_customer_on_storage_zone()

    def _validate_dedicated_customer_on_storage_zone(self):
        """Een dedicated customer is alleen zinvol op Active Storage zones."""
        if self.dedicated_customer and self.zone_type != "Active Storage":
            frappe.throw(
                _(
                    "Een dedicated klant kan alleen worden ingesteld op zones van het type "
                    "'Active Storage'. Zone type is nu '{0}'."
                ).format(self.zone_type)
            )
