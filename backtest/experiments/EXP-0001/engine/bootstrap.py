"""
Bootstrap Circular por Bloques (CBB) para EXP-0001 (§8.3, D-023).

Parámetros oficiales: bloques=20, iteraciones=10,000, semilla=20261108.
Estadístico: expectancy neta (media de pnl_neto_usdt).
Criterio obligatorio (D-023): límite inferior IC 95% > 0 estrictamente.

Bloque=10 se calcula como análisis informativo. No puede rescatar un resultado
desfavorable del método principal ni reemplazarlo.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from typing import List
from .constants import (
    BOOTSTRAP_BLOCK_SIZE, BOOTSTRAP_BLOCK_SIZE_INFO,
    BOOTSTRAP_ITER, BOOTSTRAP_SEED, BOOTSTRAP_CONF,
)
from .simulator import Trade


@dataclass
class BootstrapResult:
    block_size:    int
    n_iter:        int
    seed:          int
    ci_lower:      float    # percentil 2.5%
    ci_upper:      float    # percentil 97.5%
    ci_level:      float
    observed_mean: float
    is_official:   bool     # True = bloque 20 (obligatorio); False = bloque 10 (informativo)


def _cbb(pnls: np.ndarray, block_size: int, n_iter: int, seed: int) -> np.ndarray:
    """
    Circular Block Bootstrap.
    Retorna array de n_iter medias bootstrap.
    """
    n = len(pnls)
    rng = np.random.default_rng(seed)

    # Número de bloques necesarios para cubrir n observaciones
    n_blocks = int(np.ceil(n / block_size))
    boot_means = np.empty(n_iter)

    for it in range(n_iter):
        starts  = rng.integers(0, n, size=n_blocks)
        indices = np.concatenate([
            np.arange(s, s + block_size) % n for s in starts
        ])[:n]
        boot_means[it] = pnls[indices].mean()

    return boot_means


def run_bootstrap(trades: List[Trade]) -> tuple[BootstrapResult, BootstrapResult]:
    """
    Ejecuta CBB oficial (bloque=20) e informativo (bloque=10).
    Devuelve (resultado_oficial, resultado_informativo).
    """
    if not trades:
        empty = BootstrapResult(
            block_size=0, n_iter=0, seed=BOOTSTRAP_SEED,
            ci_lower=0.0, ci_upper=0.0, ci_level=BOOTSTRAP_CONF,
            observed_mean=0.0, is_official=True,
        )
        return empty, empty

    pnls = np.array([t.pnl_neto_usdt for t in trades], dtype=float)
    obs_mean = float(pnls.mean())

    alpha = 1.0 - BOOTSTRAP_CONF
    lo_pct = alpha / 2 * 100
    hi_pct = (1 - alpha / 2) * 100

    def _run(block_size: int, official: bool) -> BootstrapResult:
        means = _cbb(pnls, block_size=block_size, n_iter=BOOTSTRAP_ITER, seed=BOOTSTRAP_SEED)
        return BootstrapResult(
            block_size=block_size, n_iter=BOOTSTRAP_ITER, seed=BOOTSTRAP_SEED,
            ci_lower=float(np.percentile(means, lo_pct)),
            ci_upper=float(np.percentile(means, hi_pct)),
            ci_level=BOOTSTRAP_CONF,
            observed_mean=obs_mean,
            is_official=official,
        )

    return _run(BOOTSTRAP_BLOCK_SIZE, True), _run(BOOTSTRAP_BLOCK_SIZE_INFO, False)
