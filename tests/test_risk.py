"""Tests de risk.py — funciones puras sin I/O."""
import unittest
from datetime import datetime, timedelta

import risk


class CanTradeTests(unittest.TestCase):
    """can_trade() evalúa si se puede abrir una posición."""

    BASE = {
        "running": True,
        "halt_reason": None,
        "position": None,
        "trades_today": 0,
        "losses_today": 0,
        "last_trade_time": None,
        "max_trades": 3,
        "max_losses": 2,
        "min_hours": 1,
    }

    def snap(self, **overrides):
        return {**self.BASE, **overrides}

    def test_allows_fresh_state(self):
        ok, reason = risk.can_trade(self.snap())
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_blocks_when_halted(self):
        ok, reason = risk.can_trade(self.snap(halt_reason="prueba"))
        self.assertFalse(ok)
        self.assertIn("bloqueado", reason)

    def test_blocks_when_stopped(self):
        ok, reason = risk.can_trade(self.snap(running=False))
        self.assertFalse(ok)
        self.assertIn("detenido", reason)

    def test_blocks_when_position_open(self):
        ok, reason = risk.can_trade(self.snap(position={"entry_price": 1}))
        self.assertFalse(ok)
        self.assertIn("posición", reason)

    def test_blocks_at_max_trades(self):
        ok, _ = risk.can_trade(self.snap(trades_today=3))
        self.assertFalse(ok)

    def test_blocks_at_max_losses(self):
        ok, _ = risk.can_trade(self.snap(losses_today=2))
        self.assertFalse(ok)

    def test_blocks_within_min_interval(self):
        last = (datetime.now() - timedelta(minutes=30)).isoformat()
        ok, reason = risk.can_trade(self.snap(last_trade_time=last))
        self.assertFalse(ok)
        self.assertIn("0.5h", reason)

    def test_allows_after_min_interval(self):
        last = (datetime.now() - timedelta(hours=2)).isoformat()
        ok, _ = risk.can_trade(self.snap(last_trade_time=last))
        self.assertTrue(ok)

    def test_accepts_deterministic_now_param(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        last = datetime(2026, 1, 1, 10, 0, 0)  # 2 h antes
        ok, _ = risk.can_trade(
            self.snap(last_trade_time=last.isoformat()),
            now=now,
        )
        self.assertTrue(ok)


class StopLossTests(unittest.TestCase):
    def test_triggers_at_exact_threshold(self):
        self.assertTrue(risk.needs_stop_loss(100_000, 98_000, 0.02))

    def test_triggers_above_threshold(self):
        self.assertTrue(risk.needs_stop_loss(100_000, 97_000, 0.02))

    def test_no_trigger_below_threshold(self):
        self.assertFalse(risk.needs_stop_loss(100_000, 99_000, 0.02))

    def test_no_trigger_on_zero_entry(self):
        self.assertFalse(risk.needs_stop_loss(0, 90_000, 0.02))


class SignalTests(unittest.TestCase):
    def test_buy_below_threshold(self):
        self.assertTrue(risk.signal_buy(28.0, 30))

    def test_buy_at_threshold_not_triggered(self):
        self.assertFalse(risk.signal_buy(30.0, 30))

    def test_buy_none_rsi(self):
        self.assertFalse(risk.signal_buy(None, 30))

    def test_sell_above_threshold(self):
        self.assertTrue(risk.signal_sell(72.0, 70))

    def test_sell_at_threshold_not_triggered(self):
        self.assertFalse(risk.signal_sell(70.0, 70))

    def test_sell_none_rsi(self):
        self.assertFalse(risk.signal_sell(None, 70))


class ComputePnlTests(unittest.TestCase):
    def test_profit(self):
        pnl_mxn, pnl_pct = risk.compute_pnl(1_000_000, 1_020_000, 0.0005)
        self.assertAlmostEqual(pnl_mxn, 10.0)
        self.assertAlmostEqual(pnl_pct, 2.0)

    def test_loss(self):
        pnl_mxn, pnl_pct = risk.compute_pnl(1_000_000, 980_000, 0.0005)
        self.assertAlmostEqual(pnl_mxn, -10.0)
        self.assertAlmostEqual(pnl_pct, -2.0)

    def test_breakeven(self):
        pnl_mxn, pnl_pct = risk.compute_pnl(1_000_000, 1_000_000, 0.001)
        self.assertEqual(pnl_mxn, 0.0)
        self.assertEqual(pnl_pct, 0.0)

    def test_fee_reduces_profit(self):
        # Con comisión, el mismo movimiento de precio produce menos ganancia.
        pnl_sin_fee, _ = risk.compute_pnl(1_000_000, 1_020_000, 0.001)
        pnl_con_fee, _ = risk.compute_pnl(1_000_000, 1_020_000, 0.001, fee_rate=0.0078)
        self.assertLess(pnl_con_fee, pnl_sin_fee)

    def test_fee_turns_breakeven_into_loss(self):
        # Mismo precio de entrada y salida con fee 0.78%: round-trip cuesta ~1.56%.
        # entry_cost = 1000 * 1.0078 = 1007.8  |  proceeds = 1000 * 0.9922 = 992.2
        pnl_mxn, pnl_pct = risk.compute_pnl(1_000_000, 1_000_000, 0.001, fee_rate=0.0078)
        self.assertAlmostEqual(pnl_mxn, -15.6, places=4)
        self.assertLess(pnl_pct, 0)


if __name__ == "__main__":
    unittest.main()
