import frappe
from frappe import _
from frappe.model.document import Document


class StorageLocation(Document):
    def validate(self):
        self._validate_one_receiving_per_warehouse()
        self._validate_one_staging_per_warehouse()

    def _validate_one_receiving_per_warehouse(self):
        if self.location_type != "Receiving":
            return
        existing = frappe.db.get_value(
            "Storage Location",
            {
                "warehouse": self.warehouse,
                "location_type": "Receiving",
                "is_active": 1,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _(
                    "Warehouse {0} already has an active Receiving location: {1}. "
                    "Deactivate the existing one before creating another."
                ).format(self.warehouse, existing)
            )

    def _validate_one_staging_per_warehouse(self):
        if self.location_type != "Picking Staging":
            return
        existing = frappe.db.get_value(
            "Storage Location",
            {
                "warehouse": self.warehouse,
                "location_type": "Picking Staging",
                "is_active": 1,
                "name": ("!=", self.name),
            },
            "name",
        )
        if existing:
            frappe.throw(
                _(
                    "Warehouse {0} already has an active Picking Staging location: {1}. "
                    "Deactivate the existing one before creating another."
                ).format(self.warehouse, existing)
            )
