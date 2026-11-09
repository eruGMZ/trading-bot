"""
Motor de backtest EXP-0001 — Trend Following H4 BTC/USDT (preregistro v4 CONGELADO, D-024).

INSTRUCCIÓN: No ejecutar automáticamente. Requiere revisión humana de la implementación
antes de correr el Train autorizado por D-024.

Uso (después de aprobación humana):
    python backtest/experiments/EXP-0001/run_exp0001.py

Salidas: imprime métricas por consola; los resultados se guardan en
    backtest/experiments/EXP-0001/results/
"""
import sys, os, json, hashlib, datetime

# Rutas de importación
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "..", "research"))

import pandas as pd
import numpy as np

from engine.aggregator  import aggregate_h1_to_h4
from engine.indicators  import compute_indicators
from engine.simulator   import simulate
from engine.metrics     import compute_metrics, compute_train_months
from engine.bootstrap   import run_bootstrap
from engine.benchmarks  import compute_benchmarks
from engine.walkforward import run_walk_forward
from engine.evaluator   import evaluate_config, evaluate_hypothesis
from engine.constants   import CONFIGS, CAPITAL_INICIAL, WARMUP_BARS

try:
    from data_loader import load_research_data
except ImportError:
    load_research_data = None


RESULTS_DIR = os.path.join(_HERE, "results")


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────────────────────

def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_manifest() -> dict:
    engine_dir = os.path.join(_HERE, "engine")
    manifest   = {}
    for fname in sorted(os.listdir(engine_dir)):
        if fname.endswith(".py"):
            full = os.path.join(engine_dir, fname)
            manifest[f"engine/{fname}"] = _sha256(full)
    manifest["run_exp0001.py"] = _sha256(os.path.abspath(__file__))
    return manifest


def _print_separator(label: str = ""):
    print(f"\n{'─' * 70}")
    if label:
        print(f"  {label}")
        print("─" * 70)


# ─────────────────────────────────────────────────────────────────────────────
# Carga de datos
# ─────────────────────────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    if load_research_data is None:
        raise ImportError(
            "No se puede importar data_loader. "
            "Ejecutar desde el directorio raíz del proyecto."
        )
    return load_research_data()


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline por configuración
# ─────────────────────────────────────────────────────────────────────────────

def run_config(h4_ind: pd.DataFrame, config) -> dict:
    print(f"\n[{config.name}] Iniciando simulación…")
    result = simulate(h4_ind, config)

    if not result.is_valid:
        print(f"  ✗ Resultado INVÁLIDO: {result.invalid_reason}")
        return {"config": config.name, "valid": False, "reason": result.invalid_reason}

    months  = compute_train_months(result.equity_curve)
    metrics = compute_metrics(result.trades, result.equity_curve,
                              capital_inicial=CAPITAL_INICIAL, train_months=months)

    boot_official, boot_info = run_bootstrap(result.trades)

    benchmarks = compute_benchmarks(h4_ind, result.trades, result.equity_curve,
                                    warmup_bars=WARMUP_BARS)

    evaluation = evaluate_config(config.name, config.is_primary, metrics, boot_official)

    # Walk-Forward (solo si hay suficientes datos)
    train_eff_start = h4_ind["open_time"].iloc[WARMUP_BARS] if len(h4_ind) > WARMUP_BARS else None
    wf_result = None
    if train_eff_start is not None:
        wf_result = run_walk_forward(h4_ind, config, train_eff_start)

    _print_config_report(config, metrics, boot_official, boot_info,
                         benchmarks, evaluation, wf_result)

    return {
        "config":      config.name,
        "valid":       True,
        "is_primary":  config.is_primary,
        "n_trades":    metrics.n_trades,
        "sharpe":      metrics.sharpe,
        "max_dd":      metrics.max_dd,
        "pf":          metrics.profit_factor,
        "expectancy":  metrics.expectancy,
        "ops_per_month": metrics.ops_per_month,
        "ic_lower":    boot_official.ci_lower,
        "ic_upper":    boot_official.ci_upper,
        "pass":        evaluation.overall_pass,
        "criteria":    {k: {"value": v.value, "passed": v.passed}
                        for k, v in evaluation.criteria.items()},
        "bh_total_return": benchmarks.bh_total_return,
        "exposure_fraction": benchmarks.exposure_fraction,
    }


def _print_config_report(config, metrics, boot_off, boot_info, benchmarks, evaluation, wf):
    p = "✓" if evaluation.overall_pass else "✗"
    print(f"\n  Resultado: {p} {'APROBADO' if evaluation.overall_pass else 'RECHAZADO'}")
    print(f"  Operaciones:   {metrics.n_trades}")
    print(f"  Sharpe:        {metrics.sharpe:.4f}  (umbral >1.0)")
    print(f"  Max DD:        {metrics.max_dd:.4%}  (umbral <10%)")
    print(f"  Profit Factor: {metrics.profit_factor:.4f}  (umbral >1.5)")
    print(f"  Expectancy:    {metrics.expectancy:.4f} USDT  (umbral >0)")
    print(f"  Ops/mes:       {metrics.ops_per_month:.2f}  (umbral ≤8)")
    print(f"  IC 95% [{boot_off.ci_lower:.4f}, {boot_off.ci_upper:.4f}] "
          f"(bloque=20)  → límite inferior {'> 0 ✓' if boot_off.ci_lower > 0 else '≤ 0 ✗'}")
    print(f"  IC 95% [{boot_info.ci_lower:.4f}, {boot_info.ci_upper:.4f}] "
          f"(bloque=10, informativo)")
    print(f"  B&H total return: {benchmarks.bh_total_return:.2%}")
    print(f"  B&H escalado:     {benchmarks.bh_scaled_equity:.2f} USDT  "
          f"(exposición {benchmarks.exposure_fraction:.1%})")
    if wf is not None and wf.is_valid:
        print(f"\n  Walk-Forward ({len(wf.windows)} ventanas):")
        for w in wf.windows:
            sym = "✓" if w.oos_expectancy > 0 else "✗"
            print(f"    WF-{w.window_id}: OOS expectancy = {w.oos_expectancy:.4f} USDT  {sym}")
        print(f"  Estabilidad WF: {'PASS' if wf.all_oos_positive else 'FAIL'}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    _print_separator("EXP-0001 — Trend Following H4 BTC/USDT")
    print("  Preregistro: v4 CONGELADO (D-024, 2026-11-09)")
    print(f"  Inicio: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

    # Manifiesto de integridad del engine
    manifest = _build_manifest()
    _print_separator("Manifiesto de integridad")
    for fname, sha in manifest.items():
        print(f"  {fname}: {sha[:16]}…")

    # Carga y agregación de datos
    _print_separator("Carga de datos")
    h1_df = load_data()
    print(f"  H1 cargadas: {len(h1_df)} velas")
    print(f"  Rango: {h1_df['open_time'].iloc[0]} → {h1_df['open_time'].iloc[-1]}")

    h4_df  = aggregate_h1_to_h4(h1_df)
    n_disc = int(h4_df["discontinuity_before"].sum())
    print(f"  H4 completas: {len(h4_df)} velas  (discontinuidades: {n_disc})")

    h4_ind = compute_indicators(h4_df)
    n_valid = int((~h4_ind["ema200"].isna()).sum())
    print(f"  Barras con EMA200 válida: {n_valid} (calentamiento: {WARMUP_BARS} barras)")

    # Correr las 4 configuraciones
    all_results = []
    for cfg in CONFIGS:
        res = run_config(h4_ind, cfg)
        all_results.append(res)

    # Dictamen H-001
    _print_separator("Dictamen H-001")
    config_a_eval = None
    for r in all_results:
        if r.get("is_primary"):
            from engine.evaluator import EvaluationResult, CriterionResult
            crit = {k: CriterionResult(name=k, value=v["value"],
                                       threshold="", passed=v["passed"])
                    for k, v in r.get("criteria", {}).items()}
            config_a_eval = type("E", (), {
                "overall_pass": r["pass"], "criteria": crit, "config_name": r["config"]
            })()
            break

    if config_a_eval is not None:
        dictamen = evaluate_hypothesis(config_a_eval)
        print(f"  H-001: {'APROBADA' if dictamen['h001_approved'] else 'RECHAZADA'}")
        print(f"  {dictamen['reason']}")

    # Guardar resultados
    os.makedirs(RESULTS_DIR, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(RESULTS_DIR, f"train_{ts}.json")
    with open(out_path, "w") as f:
        json.dump({
            "timestamp": ts,
            "preregistration": "v4 CONGELADO D-024",
            "manifest": manifest,
            "results": all_results,
        }, f, indent=2, default=str)
    print(f"\n  Resultados guardados: {out_path}")

    _print_separator("Fin")


if __name__ == "__main__":
    main()
