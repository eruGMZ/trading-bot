"""Paper trading (dry-run simulation) exchange adapter."""

import logging
import uuid
from datetime import datetime
from decimal import Decimal

from trading_bot.core.money import quantize_btc, quantize_mxn
from trading_bot.domain.models import Quote
from trading_bot.ports.exchange import ExchangePort

log = logging.getLogger(__name__)


class PaperTradingAdapter(ExchangePort):
    """In-memory exchange simulator implementing ExchangePort for dry-run testing."""

    def __init__(
        self,
        quote_provider: ExchangePort | None = None,
        initial_mxn: Decimal = Decimal("5000.00"),
        initial_btc: Decimal = Decimal("0.00000000"),
    ) -> None:
        self._delegate = quote_provider
        self._balances: dict[str, Decimal] = {
            "mxn": quantize_mxn(initial_mxn),
            "btc": quantize_btc(initial_btc),
        }
        self._mock_quote = Quote(
            symbol="btc_mxn",
            last=Decimal("1000000.00"),
            bid=Decimal("999000.00"),
            ask=Decimal("1001000.00"),
            spread_pct=Decimal("0.002"),
            timestamp=datetime.now(),
        )

    def set_mock_quote(self, quote: Quote) -> None:
        """Explicitly set the simulated quote."""
        self._mock_quote = quote

    def get_quote(self, book: str = "btc_mxn") -> Quote:
        """Fetch real quote from delegate if configured, otherwise return mock quote."""
        if self._delegate is not None:
            return self._delegate.get_quote(book)
        return self._mock_quote

    def get_available_balance(self, asset: str) -> Decimal:
        """Return simulated in-memory balance."""
        return self._balances.get(asset.lower(), Decimal("0"))

    def place_order(
        self,
        book: str,
        side: str,
        amount_btc: Decimal | None = None,
        amount_mxn: Decimal | None = None,
    ) -> str:
        """Simulate order execution in paper-trading mode."""
        order_side = side.lower().strip()
        sim_oid = f"sim_ord_{uuid.uuid4().hex[:12]}"

        if order_side == "buy":
            if amount_mxn is None or amount_mxn <= Decimal("0"):
                raise ValueError("Buy order requires amount_mxn > 0")
            quote = self.get_quote(book)
            purchased_btc = quantize_btc(amount_mxn / quote.ask)
            cur_mxn = self._balances.get("mxn", Decimal("0"))
            cur_btc = self._balances.get("btc", Decimal("0"))
            self._balances["mxn"] = quantize_mxn(cur_mxn - amount_mxn)
            self._balances["btc"] = quantize_btc(cur_btc + purchased_btc)
            log.info(
                "[SIMULATED] BUY %s MXN on %s -> +%s BTC (oid=%s)",
                amount_mxn,
                book,
                purchased_btc,
                sim_oid,
            )
        elif order_side == "sell":
            if amount_btc is None or amount_btc <= Decimal("0"):
                raise ValueError("Sell order requires amount_btc > 0")
            quote = self.get_quote(book)
            proceeds_mxn = quantize_mxn(amount_btc * quote.bid)
            cur_btc = self._balances.get("btc", Decimal("0"))
            cur_mxn = self._balances.get("mxn", Decimal("0"))
            self._balances["btc"] = quantize_btc(cur_btc - amount_btc)
            self._balances["mxn"] = quantize_mxn(cur_mxn + proceeds_mxn)
            log.info(
                "[SIMULATED] SELL %s BTC on %s -> +%s MXN (oid=%s)",
                amount_btc,
                book,
                proceeds_mxn,
                sim_oid,
            )
        else:
            raise ValueError(f"Invalid order side: {side!r}")

        return sim_oid
