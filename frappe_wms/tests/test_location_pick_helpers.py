import unittest
from types import SimpleNamespace
from unittest.mock import patch

from frappe_wms.wms.doctype.location_pick import location_pick


class LocationPickHelperTests(unittest.TestCase):
    def test_direct_batch_entry_uses_pick_list_qty(self):
        row = SimpleNamespace(batch_no="BATCH-001", qty=5)

        self.assertEqual(
            list(location_pick._iter_pl_item_batch_entries(row)),
            [("BATCH-001", 5.0)],
        )

    def test_bundle_entries_yield_all_batches_with_absolute_qty(self):
        row = SimpleNamespace(
            name="PLI-001",
            batch_no=None,
            serial_and_batch_bundle="SABB-001",
        )
        entries = [
            SimpleNamespace(batch_no="BATCH-001", qty=-2),
            SimpleNamespace(batch_no="BATCH-002", qty=3),
            SimpleNamespace(batch_no=None, qty=1),
            SimpleNamespace(batch_no="BATCH-003", qty=0),
        ]

        with patch.object(location_pick.frappe.db, "get_all", return_value=entries):
            self.assertEqual(
                list(location_pick._iter_pl_item_batch_entries(row)),
                [("BATCH-001", 2.0), ("BATCH-002", 3.0)],
            )

    def test_bundle_name_is_loaded_when_missing_on_row(self):
        row = SimpleNamespace(name="PLI-001", batch_no=None)
        entries = [SimpleNamespace(batch_no="BATCH-001", qty=4)]

        with (
            patch.object(
                location_pick.frappe.db,
                "get_value",
                return_value="SABB-001",
            ) as get_value,
            patch.object(location_pick.frappe.db, "get_all", return_value=entries),
        ):
            self.assertEqual(
                list(location_pick._iter_pl_item_batch_entries(row)),
                [("BATCH-001", 4.0)],
            )

        get_value.assert_called_once_with(
            "Pick List Item",
            "PLI-001",
            "serial_and_batch_bundle",
        )

    def test_legacy_first_batch_helper_uses_first_bundle_entry(self):
        row = SimpleNamespace(
            name="PLI-001",
            batch_no=None,
            serial_and_batch_bundle="SABB-001",
        )
        entries = [
            SimpleNamespace(batch_no="BATCH-001", qty=2),
            SimpleNamespace(batch_no="BATCH-002", qty=3),
        ]

        with patch.object(location_pick.frappe.db, "get_all", return_value=entries):
            self.assertEqual(location_pick._get_pl_item_batch_no(row), "BATCH-001")


if __name__ == "__main__":
    unittest.main()
