import frappe
from frappe import _
from frappe.model.document import Document


class BatchLocationMovement(Document):
    def validate(self):
        if not self.from_location and not self.to_location:
            frappe.throw(_("At least one of From Location or To Location is required."))
        if self.qty <= 0:
            frappe.throw(_("Qty must be greater than zero."))
