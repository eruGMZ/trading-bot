"""Tests de integración en dry-run: flujos completos de compra, venta y stop-loss.

Usa BotState real (con archivo temporal) y parchea solo las llamadas externas
(Bitso, Telegram, RSI).
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot
from config import (
    CAPITAL_REF_MXN, DAILY_LOSS_PCT,
    MAX_LOSSES_DAY, MAX_TRADES_DAY, MIN_HOURS_BETWEEN_TRADES,
)
from exchange import format_btc
from logsafety import redact
from state import BotState
from state_store import default_state, load_state, roll_over_day, save_state
from telegram_client import is_authorized_chat

# Quote con spread muy estrecho para no activar el filtro en los tests.
_QUOTE_OK = {"last": 1_000_000.0, "bid": 999_000.0, "ask": 1_001_000.0, "spread_pct": 0.002}


class FormatBtcTests(unittest.TestCase):
    def test_truncates_never_rounds_up(self):
        self.assertEqual(format_btc(0.123456789), "0.12345678")

    def test_zero_value(self):
        self.assertEqual(format_btc(0), "0.00000000")

    def test_tiny_below_satoshi(self):
        self.assertEqual(format_btc(0.0000000049), "0.00000000")


class AuthorizedChatTests(unittest.TestCase):
    def test_matches_string_or_int_ids(self):
        self.assertTrue(is_authorized_chat("123", "123"))
        self.assertTrue(is_authorized_chat(123, "123"))

    def test_rejects_other_chats(self):
        self.assertFalse(is_authorized_chat("999", "123"))

    def test_fails_closed_without_configured_chat(self):
        self.assertFalse(is_authorized_chat("123", ""))
        self.assertFalse(is_authorized_chat("123", None))


class RedactTests(unittest.TestCase):
    def test_replaces_secrets(self):
        text = "error en /bot123:ABC/getUpdates con key K1"
        self.assertEqual(
            redact(text, ["123:ABC", "K1"]),
            "error en /bot***/getUpdates con key ***",
        )

    def test_ignores_empty_secrets(self):
        self.assertEqual(redact("hola", ["", None]), "hola")


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp  = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "state.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_gives_fresh_state(self):
        state = load_state(self.path, "dry_run", "2026-11-06")
        self.assertIsNone(state["position"])
        self.assertTrue(state["running"])

    def test_round_trip_keeps_position(self):
        state = default_state("dry_run", "2026-11-06")
        state["position"] = {"entry_price": 1000.0, "amount_btc": 0.5, "entry_time": "x"}
        save_state(self.path, state)
        loaded = load_state(self.path, "dry_run", "2026-11-07")
        self.assertEqual(loaded["position"]["amount_btc"], 0.5)

    def test_corrupt_file_raises_instead_of_resetting(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{no es json")
        with self.assertRaises(ValueError):
            load_state(self.path, "dry_run", "2026-11-06")

    def test_roll_over_day_resets_only_on_new_day(self):
        state = default_state("dry_run", "2026-11-06")
        state["trades_today"]  = 3
        state["losses_today"]  = 2
        self.assertFalse(roll_over_day(state, "2026-11-06"))
        self.assertEqual(state["trades_today"], 3)
        self.assertTrue(roll_over_day(state, "2026-11-07"))
        self.assertEqual((state["trades_today"], state["losses_today"]), (0, 0))


class TradeFlowTests(unittest.TestCase):
    """Flujo completo en dry-run con dependencias externas parcheadas."""

    def setUp(self):
        self.assertTrue(bot.IS_DRY_RUN, "estas pruebas corren solo en dry-run")
        self.tmp = tempfile.TemporaryDirectory()

        bot.bot_state = BotState(
            os.path.join(self.tmp.name, "state.json"),
            "dry_run",
            max_trades=MAX_TRADES_DAY,
            max_losses=MAX_LOSSES_DAY,
            min_hours=MIN_HOURS_BETWEEN_TRADES,
            capital_ref=CAPITAL_REF_MXN,
            daily_loss_pct=DAILY_LOSS_PCT,
        )

        # trade_log apunta a archivo temporal para no tocar la BD real.
        self._orig_tl = bot.TRADE_LOG_FILE
        bot.TRADE_LOG_FILE = os.path.join(self.tmp.name, "trades.db")
        import trade_log as tl
        tl.init_db(bot.TRADE_LOG_FILE)

        self._patches = []
        self.notify = self._patch("telegram_notify")
        self.rsi    = self._patch("read_cached_rsi", return_value=None)
        self.quote  = self._patch("bitso_get_quote", return_value=dict(_QUOTE_OK))
        self.order  = self._patch("bitso_place_order", return_value={"simulated": True})

    def tearDown(self):
        for p in self._patches:
            p.stop()
        bot.TRADE_LOG_FILE = self._orig_tl
        self.tmp.cleanup()

    def _patch(self, name, *args, **kwargs):
        p = mock.patch.object(bot, name, *args, **kwargs)
        self._patches.append(p)
        return p.start()

    def test_buy_signal_opens_position(self):
        self.rsi.return_value = 25.0
        bot._tick()
        self.assertIsNotNone(bot.bot_state.get("position"))
        self.order.assert_called_once()
        call = self.order.call_args
        self.assertEqual(call.args, ("btc_mxn", "buy"))
        self.assertIn("amount_mxn", call.kwargs)
        self.assertGreater(call.kwargs["amount_mxn"], 0)

    def test_stop_loss_sells_btc_not_mxn(self):
        self.rsi.return_value = 25.0
        bot._tick()

        self.quote.return_value = {"last": 975_000.0, "bid": 974_000.0, "ask": 976_000.0, "spread_pct": 0.002}
        self.rsi.return_value = None
        bot._tick()

        self.assertIsNone(bot.bot_state.get("position"))
        self.assertEqual(bot.bot_state.get("losses_today"), 1)
        sell_call = [c for c in self.order.call_args_list if c.args[1] == "sell"][0]
        self.assertIn("amount_btc", sell_call.kwargs)
        self.assertNotIn("amount_mxn", sell_call.kwargs)

    def test_rsi_sell_clears_position(self):
        self.rsi.return_value = 25.0
        bot._tick()
        self.rsi.return_value = 75.0
        bot._tick()
        self.assertIsNone(bot.bot_state.get("position"))

    def test_position_is_persisted_to_disk(self):
        self.rsi.return_value = 25.0
        bot._tick()
        with open(bot.bot_state._path, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertIsNotNone(saved["position"])

    def test_halt_blocks_buy(self):
        bot.bot_state.halt("prueba")
        self.rsi.return_value = 20.0
        bot._tick()
        self.order.assert_not_called()

    def test_day_change_resets_counters(self):
        bot.bot_state.set(day="1999-01-01", trades_today=3, losses_today=2)
        bot._tick()
        self.assertEqual(bot.bot_state.get("trades_today"), 0)

    def test_stopped_bot_does_not_trade(self):
        bot.bot_state.set(running=False)
        self.rsi.return_value = 20.0
        bot._tick()
        self.order.assert_not_called()

    def test_no_double_buy_without_sell(self):
        self.rsi.return_value = 25.0
        bot._tick()
        bot._tick()
        buy_calls = [c for c in self.order.call_args_list if c.args[1] == "buy"]
        self.assertEqual(len(buy_calls), 1)

    def test_wide_spread_blocks_buy(self):
        self.rsi.return_value = 25.0
        self.quote.return_value = {"last": 1_000_000.0, "bid": 990_000.0, "ask": 1_010_000.0, "spread_pct": 0.02}
        bot._tick()
        self.order.assert_not_called()

    def test_kill_switch_halts_bot(self):
        # Simula equity caído al 85% del capital de referencia (drawdown 15% > umbral 10%).
        bot.bot_state.set(pnl_total=-(CAPITAL_REF_MXN * 0.15))
        self.rsi.return_value = 20.0
        bot._tick()
        self.assertIsNotNone(bot.bot_state.get("halt_reason"))
        self.order.assert_not_called()


if __name__ == "__main__":
    unittest.main()
