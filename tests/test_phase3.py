"""Tests de Fase 3: nuevas funciones puras de risk.py y trade_log.py."""
import os
import sqlite3
import tempfile
import unittest

import risk
import trade_log


class SpreadTests(unittest.TestCase):
    def test_wide_spread_blocked(self):
        self.assertTrue(risk.spread_too_wide(0.006, 0.005))

    def test_narrow_spread_allowed(self):
        self.assertFalse(risk.spread_too_wide(0.004, 0.005))

    def test_exactly_at_limit_allowed(self):
        # El filtro es estricto: solo bloquea si es MAYOR que el límite.
        self.assertFalse(risk.spread_too_wide(0.005, 0.005))


class DrawdownTests(unittest.TestCase):
    def test_triggers_at_threshold(self):
        self.assertTrue(risk.drawdown_exceeded(9_000, 10_000, 0.10))

    def test_triggers_beyond_threshold(self):
        self.assertTrue(risk.drawdown_exceeded(8_000, 10_000, 0.10))

    def test_no_trigger_below_threshold(self):
        self.assertFalse(risk.drawdown_exceeded(9_500, 10_000, 0.10))

    def test_no_trigger_with_zero_peak(self):
        self.assertFalse(risk.drawdown_exceeded(0, 0, 0.10))


class DailyLossCutTests(unittest.TestCase):
    """can_trade() bloquea cuando pnl_today supera el límite diario en MXN."""

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
        "capital_ref": 5000.0,
        "daily_loss_pct": 0.03,  # 3% = -150 MXN
    }

    def snap(self, **overrides):
        return {**self.BASE, **overrides}

    def test_allows_when_within_limit(self):
        ok, _ = risk.can_trade(self.snap(pnl_today=-100.0))
        self.assertTrue(ok)

    def test_blocks_when_exactly_at_limit(self):
        # -150 MXN = 3% de 5000
        ok, reason = risk.can_trade(self.snap(pnl_today=-150.01))
        self.assertFalse(ok)
        self.assertIn("pérdida diaria", reason)

    def test_allows_on_zero_pnl(self):
        ok, _ = risk.can_trade(self.snap(pnl_today=0.0))
        self.assertTrue(ok)


class PositionSizeTests(unittest.TestCase):
    def test_basic_calculation(self):
        # capital=5000, risk=1%, stop=2% → 5000*0.01/0.02 = 2500, capped at 500
        size = risk.position_size_mxn(5000, 0.01, 0.02, 500)
        self.assertEqual(size, 500.0)

    def test_uncapped_when_below_max(self):
        # capital=1000, risk=1%, stop=10% → 1000*0.01/0.10 = 100, cap=500 → 100
        size = risk.position_size_mxn(1000, 0.01, 0.10, 500)
        self.assertAlmostEqual(size, 100.0)

    def test_minimum_is_one_mxn(self):
        size = risk.position_size_mxn(0, 0.01, 0.02, 500)
        self.assertEqual(size, 1.0)

    def test_zero_stop_does_not_raise(self):
        size = risk.position_size_mxn(5000, 0.01, 0, 500)
        self.assertGreaterEqual(size, 1.0)


class ComputeMetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db  = os.path.join(self.tmp.name, "trades.db")
        trade_log.init_db(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def _close(self, pnl):
        trade_log.log_close(self.db, "close", 1_000_000, 1_000_000, 0.001,
                            pnl, pnl / 10, "rsi_sell", "dry_run")

    def test_no_trades_returns_zero_total(self):
        m = trade_log.compute_metrics(self.db)
        self.assertEqual(m["total"], 0)

    def test_all_wins(self):
        self._close(100); self._close(50)
        m = trade_log.compute_metrics(self.db)
        self.assertEqual(m["total"], 2)
        self.assertAlmostEqual(m["win_rate"], 100.0)
        self.assertEqual(m["profit_factor"], float("inf"))
        self.assertAlmostEqual(m["max_drawdown_mxn"], 0.0)

    def test_all_losses(self):
        self._close(-80); self._close(-40)
        m = trade_log.compute_metrics(self.db)
        self.assertAlmostEqual(m["win_rate"], 0.0)
        self.assertAlmostEqual(m["profit_factor"], 0.0)

    def test_mixed_win_rate_and_expectancy(self):
        self._close(60); self._close(-20); self._close(40)
        m = trade_log.compute_metrics(self.db)
        self.assertAlmostEqual(m["win_rate"], 200/3, places=1)   # 2/3
        self.assertAlmostEqual(m["expectancy"], 80/3, places=4)  # (60-20+40)/3

    def test_profit_factor(self):
        self._close(90); self._close(-30)
        m = trade_log.compute_metrics(self.db)
        self.assertAlmostEqual(m["profit_factor"], 3.0)  # 90 / 30

    def test_max_drawdown(self):
        # +100, -60, +20 → cumPnL: 100, 40, 60 → DD máx = 100-40 = 60
        self._close(100); self._close(-60); self._close(20)
        m = trade_log.compute_metrics(self.db)
        self.assertAlmostEqual(m["max_drawdown_mxn"], 60.0)

    def test_open_rows_excluded(self):
        trade_log.log_open(self.db, 1_000_000, 0.001, 1000.0, "rsi_buy", "dry_run")
        m = trade_log.compute_metrics(self.db)
        self.assertEqual(m["total"], 0)


class TradeLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db  = os.path.join(self.tmp.name, "trades.db")
        trade_log.init_db(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def _rows(self):
        with sqlite3.connect(self.db) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT * FROM trades ORDER BY id")]

    def test_log_open_inserts_row(self):
        trade_log.log_open(self.db, 1_000_000, 0.0005, 500.0, "rsi_buy", "dry_run")
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["event"],       "open")
        self.assertEqual(r["price"],       1_000_000)
        self.assertEqual(r["amount_mxn"],  500.0)
        self.assertIsNone(r["pnl_mxn"])

    def test_log_close_inserts_row(self):
        trade_log.log_close(
            self.db, "close",
            1_000_000, 1_020_000, 0.0005,
            10.0, 2.0, "rsi_sell", "dry_run",
        )
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["event"],       "close")
        self.assertEqual(r["pnl_mxn"],     10.0)
        self.assertEqual(r["entry_price"], 1_000_000)

    def test_stop_loss_event_stored(self):
        trade_log.log_close(
            self.db, "stop_loss",
            1_000_000, 980_000, 0.0005,
            -10.0, -2.0, "stop_loss", "dry_run",
        )
        rows = self._rows()
        self.assertEqual(rows[0]["event"], "stop_loss")

    def test_init_db_idempotent(self):
        trade_log.init_db(self.db)  # segunda vez no falla
        trade_log.log_open(self.db, 1_000_000, 0.0005, 500.0, "rsi_buy", "dry_run")
        self.assertEqual(len(self._rows()), 1)


if __name__ == "__main__":
    unittest.main()
