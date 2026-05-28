import frappe
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
                f"Warehouse {self.warehouse} already has an active Receiving location: {existing}. "
                "Deactivate the existing one before creating another."
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
                f"Warehouse {self.warehouse} already has an active Picking Staging location: {existing}. "
                "Deactivate the existing one before creating another."
            )
