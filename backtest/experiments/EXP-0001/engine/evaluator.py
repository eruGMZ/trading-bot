"""
Evaluación PASS/FAIL por criterio para EXP-0001 (§5, D-015, D-023).

Criterios de aprobación de Train (todos obligatorios):
  - n_trades ≥ 50
  - Sharpe > 1.0
  - Max DD < 10% (< 0.10)
  - Profit Factor > 1.5
  - Expectancy > 0 USDT
  - Ops/mes promedio ≤ 8
  - IC 95% CBB: límite inferior > 0 (D-023)

Regla de selección (§6): H-001 se aprueba si y solo si A supera todos los criterios.
Si A falla, EXP-0001 cierra sin candidato independientemente de B/C/D.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional
from .constants import (
    MIN_TRADES, MIN_SHARPE, MAX_DD, MIN_PF,
    MIN_EXPECTANCY, MAX_TRADES_MONTH,
)
from .metrics import Metrics
from .bootstrap import BootstrapResult


@dataclass
class CriterionResult:
    name:     str
    value:    float
    threshold: str
    passed:   bool


@dataclass
class EvaluationResult:
    config_name:  str
    is_primary:   bool
    criteria:     Dict[str, CriterionResult]
    overall_pass: bool
    notes:        str = ""


def evaluate_config(
    config_name: str,
    is_primary: bool,
    metrics: Metrics,
    bootstrap_official: BootstrapResult,
) -> EvaluationResult:
    """Evalúa una configuración contra todos los criterios de Train."""

    criteria: Dict[str, CriterionResult] = {}

    def add(name: str, value: float, threshold: str, passed: bool):
        criteria[name] = CriterionResult(name=name, value=value,
                                          threshold=threshold, passed=passed)

    add("n_trades",    float(metrics.n_trades), f">= {MIN_TRADES}",
        metrics.n_trades >= MIN_TRADES)

    add("sharpe",      metrics.sharpe, f"> {MIN_SHARPE}",
        metrics.sharpe > MIN_SHARPE)

    add("max_dd",      metrics.max_dd, f"< {MAX_DD}",
        metrics.max_dd < MAX_DD)

    add("profit_factor", metrics.profit_factor, f"> {MIN_PF}",
        metrics.profit_factor > MIN_PF)

    add("expectancy",  metrics.expectancy, f"> {MIN_EXPECTANCY} USDT",
        metrics.expectancy > MIN_EXPECTANCY)

    if not _isnan(metrics.ops_per_month):
        add("ops_per_month", metrics.ops_per_month, f"<= {MAX_TRADES_MONTH}",
            metrics.ops_per_month <= MAX_TRADES_MONTH)

    add("ic_lower",    bootstrap_official.ci_lower, "> 0 (D-023)",
        bootstrap_official.ci_lower > 0)

    overall = all(c.passed for c in criteria.values())
    notes   = "" if overall else "Uno o más criterios no superados."

    return EvaluationResult(
        config_name=config_name,
        is_primary=is_primary,
        criteria=criteria,
        overall_pass=overall,
        notes=notes,
    )


def evaluate_hypothesis(config_a_result: EvaluationResult) -> dict:
    """
    Determina el dictamen de H-001 según la regla §6.
    H-001 aprobada si y solo si la configuración A pasa.
    """
    if config_a_result.overall_pass:
        return {"h001_approved": True,
                "reason": "Configuración A superó todos los criterios de Train."}
    else:
        failed = [name for name, c in config_a_result.criteria.items() if not c.passed]
        return {"h001_approved": False,
                "reason": f"Configuración A falló en: {failed}. EXP-0001 cierra sin candidato."}


def _isnan(v) -> bool:
    import math
    try:
        return math.isnan(v)
    except TypeError:
        return False
