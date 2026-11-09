"""Pruebas del bootstrap CBB (§8.3, D-023)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import pytest
from engine.bootstrap import run_bootstrap, _cbb
from engine.simulator import Trade
from engine.constants import BOOTSTRAP_SEED, BOOTSTRAP_BLOCK_SIZE


def _make_trade(pnl: float) -> Trade:
    t0 = pd.Timestamp("2023-06-01", tz="UTC")
    return Trade(
        open_time_entrada=t0, open_time_salida=t0 + pd.Timedelta("4h"),
        precio_entrada=100.0, precio_salida=100.0,
        exit_type="stop_normal", stop_inicial=90.0, stop_salida=90.0,
        tamano_btc=1.0, pnl_bruto_usdt=pnl, costo_usdt=0.0,
        pnl_neto_usdt=pnl, equity_pre_usdt=150.0, equity_post_usdt=150.0 + pnl,
        config_name="EXP-0001-A",
    )


class TestCBB:
    def test_reproducibility_with_same_seed(self):
        pnls = np.array([1.0, -0.5, 2.0, -1.0, 1.5] * 10, dtype=float)
        m1 = _cbb(pnls, block_size=5, n_iter=100, seed=42)
        m2 = _cbb(pnls, block_size=5, n_iter=100, seed=42)
        np.testing.assert_array_equal(m1, m2)

    def test_different_seed_different_result(self):
        # PnLs con alta varianza para que distintas semillas produzcan distintos resultados
        rng  = np.random.default_rng(0)
        pnls = rng.normal(0, 5, 100)
        m1 = _cbb(pnls, block_size=5, n_iter=200, seed=42)
        m2 = _cbb(pnls, block_size=5, n_iter=200, seed=99)
        assert not np.array_equal(m1, m2)

    def test_output_length(self):
        pnls = np.ones(50)
        m = _cbb(pnls, block_size=10, n_iter=500, seed=0)
        assert len(m) == 500

    def test_constant_pnls_give_exact_mean(self):
        """Con PnL constante, todas las medias bootstrap son iguales al valor."""
        pnls = np.full(50, 3.0)
        m = _cbb(pnls, block_size=10, n_iter=100, seed=0)
        np.testing.assert_allclose(m, 3.0, atol=1e-10)


class TestRunBootstrap:
    def test_empty_trades(self):
        official, info = run_bootstrap([])
        assert official.ci_lower == 0.0
        assert info.ci_lower == 0.0

    def test_official_uses_block_20(self):
        trades = [_make_trade(1.0)] * 60
        official, _ = run_bootstrap(trades)
        assert official.block_size == BOOTSTRAP_BLOCK_SIZE
        assert official.is_official

    def test_informative_uses_block_10(self):
        trades = [_make_trade(1.0)] * 60
        _, info = run_bootstrap(trades)
        assert info.block_size == 10
        assert not info.is_official

    def test_seed_matches_preregistration(self):
        trades = [_make_trade(1.0)] * 60
        official, _ = run_bootstrap(trades)
        assert official.seed == BOOTSTRAP_SEED

    def test_preregistration_seed_20261108(self):
        """Verificación explícita de la semilla D-023."""
        assert BOOTSTRAP_SEED == 20261108

    def test_ci_bounds_ordered(self):
        trades = [_make_trade(v) for v in np.random.default_rng(1).normal(1.0, 0.5, 60)]
        official, _ = run_bootstrap(trades)
        assert official.ci_lower <= official.observed_mean <= official.ci_upper

    def test_all_positive_pnls_ci_lower_above_zero(self):
        """Con todos los PnL positivos, el límite inferior IC debe ser > 0."""
        trades = [_make_trade(2.0)] * 60
        official, _ = run_bootstrap(trades)
        assert official.ci_lower > 0

    def test_all_negative_pnls_ci_upper_below_zero(self):
        """Con todos los PnL negativos, el límite superior IC debe ser < 0."""
        trades = [_make_trade(-2.0)] * 60
        official, _ = run_bootstrap(trades)
        assert official.ci_upper < 0

    def test_n_iter_10000(self):
        from engine.constants import BOOTSTRAP_ITER
        assert BOOTSTRAP_ITER == 10_000

    def test_ci_level_95(self):
        from engine.constants import BOOTSTRAP_CONF
        assert BOOTSTRAP_CONF == 0.95
