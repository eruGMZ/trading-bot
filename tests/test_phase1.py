import json
import os
import tempfile
import unittest
from unittest import mock

import bot
from exchange import format_btc
from logsafety import redact
from state_store import default_state, load_state, roll_over_day, save_state
from telegram_client import is_authorized_chat


class FormatBtcTests(unittest.TestCase):
    def test_truncates_never_rounds_up(self):
        self.assertEqual(format_btc(0.123456789), "0.12345678")

    def test_zero_and_tiny_values(self):
        self.assertEqual(format_btc(0), "0.00000000")
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
        self.tmp = tempfile.TemporaryDirectory()
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
        state["trades_today"] = 3
        state["losses_today"] = 2
        self.assertFalse(roll_over_day(state, "2026-11-06"))
        self.assertEqual(state["trades_today"], 3)
        self.assertTrue(roll_over_day(state, "2026-11-07"))
        self.assertEqual((state["trades_today"], state["losses_today"]), (0, 0))


class TradeFlowTests(unittest.TestCase):
    """Flujo completo en dry-run con Bitso, Telegram y RSI simulados."""

    def setUp(self):
        self.assertTrue(bot.IS_DRY_RUN, "estas pruebas corren solo en dry-run")
        self.tmp = tempfile.TemporaryDirectory()
        self._patches = []
        self.notify = self._patch("telegram_notify")
        self.rsi = self._patch("read_cached_rsi", return_value=None)
        self.price = self._patch("bitso_get_ticker", return_value=1_000_000.0)
        self.order = self._patch("bitso_place_order", return_value={"simulated": True})
        self._patch("STATE_FILE", os.path.join(self.tmp.name, "state.json"))
        bot._init_state()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self.tmp.cleanup()

    def _patch(self, name, *args, **kwargs):
        p = mock.patch.object(bot, name, *args, **kwargs)
        self._patches.append(p)
        return p.start()

    def test_buy_then_stop_loss_sells_btc_not_mxn(self):
        self.rsi.return_value = 25.0
        bot._tick()
        self.assertIsNotNone(bot.state["position"])
        self.order.assert_called_with("btc_mxn", "buy", amount_mxn=500.0)

        self.price.return_value = 975_000.0  # -2.5%, supera el stop de 2%
        self.rsi.return_value = None
        bot._tick()

        self.assertIsNone(bot.state["position"])
        self.assertEqual(bot.state["losses_today"], 1)
        _, kwargs = self.order.call_args
        self.assertEqual(self.order.call_args.args, ("btc_mxn", "sell"))
        self.assertAlmostEqual(kwargs["amount_btc"], 0.0005)
        self.assertNotIn("amount_mxn", kwargs)

    def test_position_is_persisted(self):
        self.rsi.return_value = 25.0
        bot._tick()
        with open(bot.STATE_FILE, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertIsNotNone(saved["position"])

    def test_halt_blocks_buy(self):
        bot.state["halt_reason"] = "prueba"
        self.rsi.return_value = 20.0
        bot._tick()
        self.order.assert_not_called()
        self.assertIsNone(bot.state["position"])

    def test_day_change_resets_counters(self):
        bot.state["day"] = "1999-01-01"
        bot.state["trades_today"] = 3
        bot._roll_day()
        self.assertEqual(bot.state["trades_today"], 0)

    def test_stopped_bot_does_nothing(self):
        bot.state["running"] = False
        self.rsi.return_value = 20.0
        bot._tick()
        self.order.assert_not_called()


if __name__ == "__main__":
    unittest.main()
