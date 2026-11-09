"""Startup and daily balance reconciliation use cases."""

import logging
from decimal import Decimal

from trading_bot.application.state_manager import StateManager
from trading_bot.config.settings import BotSettings
from trading_bot.core.money import format_btc, format_mxn
from trading_bot.ports.exchange import ExchangePort
from trading_bot.ports.notifier import NotifierPort

log = logging.getLogger(__name__)

# Bitso may charge taker fees in BTC; allow up to 2% drift for fee/fill variance
DEFAULT_RECONCILE_TOLERANCE = Decimal("0.98")


def reconcile_on_startup(
    state_mgr: StateManager,
    exchange: ExchangePort,
    settings: BotSettings,
    notifier: NotifierPort | None = None,
) -> bool:
    """Validate consistency between local state and exchange balance on bot startup.

    Halts the bot if critical discrepancies are discovered to prevent unmanaged
    positions from trading without stop-losses.

    Returns:
        True if reconciliation passed, False if the bot was halted.
    """
    snap = state_mgr.snapshot()
    stored_mode = snap.mode

    if snap.position is not None and stored_mode != settings.bot_mode:
        reason = (
            f"position opened in mode {stored_mode!r}, "
            f"but starting in {settings.bot_mode!r}"
        )
        state_mgr.halt(reason)
        if notifier is not None:
            notifier.notify(f"{settings.mode_tag}⛔ RECONCILIATION HALT: {reason}")
        return False

    if settings.is_dry_run:
        state_mgr.set(mode=settings.bot_mode)
        log.info("Startup reconciliation skipped in dry-run mode")
        return True

    try:
        btc = exchange.get_available_balance("btc")
        price = exchange.get_quote(settings.book).last
    except Exception as err:
        reason = f"failed to query exchange during startup reconciliation: {err}"
        state_mgr.halt(reason)
        if notifier is not None:
            notifier.notify(f"{settings.mode_tag}⛔ RECONCILIATION HALT: {reason}")
        return False

    if snap.position is None:
        dust_val_mxn = btc * price
        if dust_val_mxn >= settings.reconcile_dust_mxn:
            reason = (
                f"exchange holds {format_btc(btc)} BTC ({format_mxn(dust_val_mxn)} MXN) "
                f"without an active position recorded"
            )
            state_mgr.halt(reason)
            if notifier is not None:
                notifier.notify(f"{settings.mode_tag}⛔ RECONCILIATION HALT: {reason}")
            return False
    else:
        expected_btc = snap.position.amount_btc
        if btc < expected_btc * DEFAULT_RECONCILE_TOLERANCE:
            reason = (
                f"recorded position of {format_btc(expected_btc)} BTC, "
                f"but exchange only has {format_btc(btc)} BTC"
            )
            state_mgr.halt(reason)
            if notifier is not None:
                notifier.notify(f"{settings.mode_tag}⛔ RECONCILIATION HALT: {reason}")
            return False

    state_mgr.set(mode=settings.bot_mode)
    log.info("Startup reconciliation successful — available BTC: %s", format_btc(btc))
    return True


def reconcile_daily(
    state_mgr: StateManager,
    exchange: ExchangePort,
    settings: BotSettings,
    notifier: NotifierPort | None = None,
) -> bool:
    """Compare exchange balance against internal state during daily routine checks.

    Returns:
        True if balance aligns within dust thresholds, False if critical drift halted the bot.
    """
    if settings.is_dry_run:
        return True

    snap = state_mgr.snapshot()
    expected_btc = snap.position.amount_btc if snap.position else Decimal("0")

    try:
        actual_btc = exchange.get_available_balance("btc")
        price = exchange.get_quote(settings.book).last
    except Exception as err:
        log.warning("Daily balance reconciliation failed to query exchange: %s", err)
        return False

    delta_btc = abs(actual_btc - expected_btc)
    delta_mxn = delta_btc * price

    if delta_mxn < settings.reconcile_dust_mxn:
        log.info(
            "Daily reconciliation OK — drift: %s BTC (%s MXN)",
            format_btc(delta_btc),
            format_mxn(delta_mxn),
        )
        return True

    msg = (
        f"⚠️ Daily reconciliation discrepancy: {format_btc(delta_btc)} BTC "
        f"({format_mxn(delta_mxn)} MXN)\n"
        f"Expected: {format_btc(expected_btc)} BTC | Real in Bitso: {format_btc(actual_btc)} BTC"
    )
    log.warning(msg)
    if notifier is not None:
        notifier.notify(f"{settings.mode_tag}{msg}")

    # Critical discrepancy threshold (10x dust limit) triggers a hard halt
    critical_threshold = settings.reconcile_dust_mxn * Decimal("10")
    if delta_mxn >= critical_threshold:
        state_mgr.halt(f"critical balance discrepancy in daily check: {format_mxn(delta_mxn)} MXN")
        return False

    return True
