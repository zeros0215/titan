import tempfile
import unittest
from pathlib import Path

from research.paper_grid import PaperGridRepository, empty_state, observe, start, stop


class PaperGridTest(unittest.TestCase):
    def test_start_buys_current_price_and_charges_fee(self):
        state = start(empty_state(), 6830)
        self.assertEqual(1, state["cycle_buys"])
        self.assertEqual(6830, state["lots"][0]["entry_price"])
        self.assertEqual(100, state["lots"][0]["quantity"])
        self.assertEqual(6965, state["lots"][0]["target_price"])
        self.assertEqual(6695, state["next_buy_price"])
        self.assertAlmostEqual(102.45, state["fees"])
        self.assertAlmostEqual(-102.45, state["net_profit_before_tax"])
        self.assertEqual(["BUY_FILLED", "START"], [x["type"] for x in state["events"]])
        self.assertEqual(0, state["real_order_requests"])

    def test_duplicate_start_preserves_running_and_halted_state(self):
        from copy import deepcopy
        running = observe(start(empty_state(), 5000), 4900)
        halted = observe(deepcopy(running), {"close": 4750, "change_rate": -0.05})
        for state in (running, halted):
            before = deepcopy(state)
            self.assertEqual(before, start(state, 6000))
            self.assertEqual(before, start(state, 6827))

    def test_invalid_quotes_preserve_trades_and_recover(self):
        from copy import deepcopy
        state = observe(start(empty_state(), 5000), 4900)
        before = deepcopy(state)
        for quote in ({"close": 5001}, {"close": 4800, "open": 4999},
                      {"close": 4800.1}, {"close": 0}):
            state = observe(state, quote)
            self.assertTrue(state["quote_warning"])
            self.assertEqual(quote, state["raw_quote"])
            for key in ("lots", "events", "fees", "current_price", "updated_at",
                        "status", "next_buy_price", "net_profit_before_tax"):
                self.assertEqual(before[key], state[key])
        state = observe(state, 5000)
        self.assertIsNone(state["quote_warning"])
        self.assertEqual([5000], [x["entry_price"] for x in state["lots"]])

    def test_invalid_start_keeps_grid_stopped(self):
        state = start(empty_state(), 6827)
        self.assertEqual("STOPPED", state["status"])
        self.assertIsNone(state["anchor_price"])
        self.assertEqual([], state["events"])
        self.assertTrue(state["quote_warning"])
        self.assertEqual("RUNNING", start(state, 6830)["status"])

    def test_builds_five_lots_and_never_exceeds_500_shares(self):
        state = start(empty_state(), 5000)
        for price in (4900, 4800, 4700, 4600, 4500):
            state = observe(state, price)
        self.assertEqual(500, sum(x["quantity"] for x in state["lots"]))
        self.assertIsNone(state["next_buy_price"])
        self.assertEqual(5, len(observe(state, 4400)["lots"]))

    def test_each_lot_sells_at_its_own_target(self):
        state = observe(start(empty_state(), 5000), 4900)
        state = observe(state, 4800)
        state = observe(state, 4900)
        self.assertEqual([5000, 4900], [x["entry_price"] for x in state["lots"]])
        self.assertEqual(10000, state["gross_profit"])

    def test_sell_reopens_one_slot_ten_won_below_fill(self):
        state = observe(start(empty_state(), 5000), 5100)
        self.assertEqual([], state["lots"])
        self.assertEqual(5090, state["next_buy_price"])
        self.assertEqual(0, state["cycle_buys"])
        state = observe(state, 5090)
        self.assertEqual([5090], [lot["entry_price"] for lot in state["lots"]])

    def test_partial_sell_reopens_one_slot_ten_won_below_fill(self):
        state = observe(start(empty_state(), 5000), 4900)
        state = observe(state, 5000)
        self.assertEqual([5000], [lot["entry_price"] for lot in state["lots"]])
        self.assertEqual(4990, state["next_buy_price"])
        self.assertEqual(1, state["cycle_buys"])

    def test_migrates_closed_previous_cycle_to_ten_won_reentry(self):
        previous = empty_state()
        previous.update({
            "schema_version": 2,
            "status": "RUNNING",
            "next_buy_price": 5010,
            "events": [{"type": "SELL_FILLED", "sell_price": 5110}],
        })
        upgraded = start(previous, 6000)
        self.assertEqual(5100, upgraded["next_buy_price"])

    def test_open_lots_do_not_reset_cycle_next_day(self):
        state = start(empty_state(), {"close": 5000, "date": "20260901"})
        state = observe(state, {"close": 4900, "date": "20260901"})
        state = observe(state, {"close": 4800, "date": "20260902"})
        self.assertEqual(3, state["cycle_buys"])
        self.assertTrue(state["overnight_holding"])

    def test_halts_new_buys_on_five_percent_drop_and_keeps_sell(self):
        state = observe(start(empty_state(), 5000), 4900)
        state = observe(state, {"close": 4750, "change_rate": -0.05,
                                "open": 4900})
        self.assertEqual("BUY_HALTED", state["status"])
        self.assertEqual(2, len(state["lots"]))
        self.assertEqual(("SELL", 5000),
                         (state["order_side"], state["order_price"]))

    def test_halts_on_three_percent_opening_gap(self):
        state = start(empty_state(), 5000)
        state = observe(state, {"close": 4850, "open": 4850,
                                "change_rate": -0.03})
        self.assertEqual("BUY_HALTED", state["status"])
        self.assertIn("갭 하락", state["halt_reason"])

    def test_market_halt_does_not_resume_until_next_date(self):
        state = start(empty_state(), {"close": 5000, "date": "20260901"})
        state = observe(state, {"close": 4750, "change_rate": -0.05,
                                "date": "20260901"})
        state = observe(state, {"close": 4900, "change_rate": -0.02,
                                "date": "20260901"})
        self.assertEqual("BUY_HALTED", state["status"])
        self.assertEqual(1, len(state["lots"]))
        state = observe(state, {"close": 4900, "change_rate": -0.02,
                                "date": "20260902"})
        self.assertEqual("RUNNING", state["status"])
        self.assertEqual(2, len(state["lots"]))

    def test_spacing_adapts_after_large_price_change(self):
        fixed = start(empty_state(), 5000)
        adaptive = start(empty_state(), 8000)
        self.assertEqual((100, "FIXED_100"),
                         (fixed["spacing"], fixed["spacing_mode"]))
        self.assertEqual((160, "ADAPTIVE_2_PERCENT"),
                         (adaptive["spacing"], adaptive["spacing_mode"]))

    def test_stop_preserves_open_lots(self):
        state = stop(observe(start(empty_state(), 5000), 4900))
        self.assertEqual(2, len(state["lots"]))
        state = start(state, 4800)
        self.assertEqual(("SELL", 5000),
                         (state["order_side"], state["order_price"]))

    def test_repository_round_trip_and_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = PaperGridRepository(Path(directory) / "state.json")
            repository.save(start(repository.load(), 5000))
            self.assertEqual("RUNNING", repository.load()["status"])
            self.assertEqual("STOPPED", repository.reset()["status"])


if __name__ == "__main__":
    unittest.main()
