import unittest
from unittest.mock import patch

from frappe_wms.wms.events import utils


class StockHelperLockTests(unittest.TestCase):
    def test_lock_storage_locations_sorts_and_deduplicates_names(self):
        with patch.object(utils.frappe.db, "sql") as sql:
            utils._lock_storage_locations("LOC-B", None, "LOC-A", "LOC-B")

        sql.assert_called_once()
        query, values = sql.call_args.args
        self.assertIn("FOR UPDATE", query)
        self.assertEqual(values, {"locations": ("LOC-A", "LOC-B")})

    def test_lock_storage_locations_skips_empty_input(self):
        with patch.object(utils.frappe.db, "sql") as sql:
            utils._lock_storage_locations(None, "")

        sql.assert_not_called()

    def test_move_to_same_location_is_noop(self):
        with (
            patch.object(utils.frappe.db, "sql") as sql,
            patch.object(utils.frappe.db, "get_value") as get_value,
        ):
            utils.move_location_qty(
                item_code="ITEM-001",
                batch_no="BATCH-001",
                warehouse="WH-001",
                from_location="LOC-001",
                to_location="LOC-001",
                qty=1,
                ref_doctype="Unit Test",
                ref_name="UNIT-001",
            )

        sql.assert_not_called()
        get_value.assert_not_called()


if __name__ == "__main__":
    unittest.main()
