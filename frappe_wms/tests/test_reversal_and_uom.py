import unittest
from types import SimpleNamespace
from unittest.mock import patch, call

from frappe_wms.wms.events import utils


class IterBatchEntriesUomTests(unittest.TestCase):
    def test_legacy_row_prefers_stock_qty(self):
        row = SimpleNamespace(batch_no="BATCH-001", qty=2, stock_qty=24)
        self.assertEqual(list(utils.iter_batch_entries(row)), [("BATCH-001", 24.0)])

    def test_legacy_row_falls_back_to_conversion_factor(self):
        row = SimpleNamespace(
            batch_no="BATCH-001", qty=2, stock_qty=0, conversion_factor=12
        )
        self.assertEqual(list(utils.iter_batch_entries(row)), [("BATCH-001", 24.0)])

    def test_legacy_row_without_conversion_uses_qty(self):
        row = SimpleNamespace(batch_no="BATCH-001", qty=5)
        self.assertEqual(list(utils.iter_batch_entries(row)), [("BATCH-001", 5.0)])


class ReverseReferenceMovementsTests(unittest.TestCase):
    def _movement(self, **kwargs):
        base = {
            "name": "MOV-001",
            "item_code": "ITEM-001",
            "batch_no": "BATCH-001",
            "warehouse": "WH-001",
            "from_location": None,
            "to_location": None,
            "qty": 10,
        }
        base.update(kwargs)
        return SimpleNamespace(**base)

    def test_add_is_reversed_as_deduct(self):
        movements = [self._movement(to_location="RECV")]
        with (
            patch.object(utils.frappe.db, "get_all", return_value=movements),
            patch.object(utils, "_get_available_qty", return_value=10.0),
            patch.object(utils, "deduct_location_qty") as deduct,
            patch.object(utils, "add_location_qty") as add,
            patch.object(utils, "move_location_qty") as move,
        ):
            utils.reverse_reference_movements("Purchase Receipt", "PR-001")

        deduct.assert_called_once()
        self.assertEqual(deduct.call_args.kwargs["storage_location"], "RECV")
        self.assertEqual(deduct.call_args.kwargs["qty"], 10)
        self.assertEqual(deduct.call_args.kwargs["movement_type"], "Reversal")
        add.assert_not_called()
        move.assert_not_called()

    def test_deduct_is_reversed_as_add(self):
        movements = [self._movement(from_location="STAGE")]
        with (
            patch.object(utils.frappe.db, "get_all", return_value=movements),
            patch.object(utils, "deduct_location_qty") as deduct,
            patch.object(utils, "add_location_qty") as add,
        ):
            utils.reverse_reference_movements("Delivery Note", "DN-001")

        add.assert_called_once()
        self.assertEqual(add.call_args.kwargs["storage_location"], "STAGE")
        deduct.assert_not_called()

    def test_move_is_reversed_backwards(self):
        movements = [self._movement(from_location="A-01", to_location="STAGE")]
        with (
            patch.object(utils.frappe.db, "get_all", return_value=movements),
            patch.object(utils, "_get_available_qty", return_value=10.0),
            patch.object(utils, "move_location_qty") as move,
        ):
            utils.reverse_reference_movements("Location Pick", "LP-001")

        move.assert_called_once()
        self.assertEqual(move.call_args.kwargs["from_location"], "STAGE")
        self.assertEqual(move.call_args.kwargs["to_location"], "A-01")

    def test_shortfall_is_capped_and_reported(self):
        movements = [self._movement(to_location="RECV", qty=10)]
        with (
            patch.object(utils.frappe.db, "get_all", return_value=movements),
            patch.object(utils, "_get_available_qty", return_value=4.0),
            patch.object(utils, "deduct_location_qty") as deduct,
            patch.object(utils.frappe, "msgprint") as msgprint,
            patch.object(utils.frappe, "log_error") as log_error,
        ):
            utils.reverse_reference_movements("Purchase Receipt", "PR-001")

        self.assertEqual(deduct.call_args.kwargs["qty"], 4.0)
        msgprint.assert_called_once()
        log_error.assert_called_once()

    def test_existing_reversals_are_excluded_from_replay(self):
        with patch.object(utils.frappe.db, "get_all", return_value=[]) as get_all:
            utils.reverse_reference_movements("Stock Entry", "SE-001")

        filters = get_all.call_args.kwargs["filters"]
        self.assertEqual(filters["movement_type"], ["!=", "Reversal"])


if __name__ == "__main__":
    unittest.main()
