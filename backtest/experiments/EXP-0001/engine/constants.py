"""Constantes del preregistro EXP-0001 v4 (CONGELADO, D-024)."""
from dataclasses import dataclass

# Capital y riesgo (D-022, §3.6)
CAPITAL_INICIAL = 150.00
RISK_PER_TRADE = 0.005      # 0.5% del equity actualizado

# Costos (§4, D-021)
FEE_ADVERSO = 0.003         # 0.30% round-trip adverso
FEE_BASE = 0.0022           # 0.22% round-trip base

# Límite fiscal (D-014)
MAX_TRADES_MONTH = 8

# Tamaño mínimo BTC (§9, M-5)
STEP_SIZE = 0.00001

# Indicadores (§3.2, §3.4)
EMA_PERIOD = 200
EMA_ALPHA = 2.0 / (EMA_PERIOD + 1)   # = 2/201
ATR_PERIOD = 14
ATR_ALPHA = 1.0 / ATR_PERIOD          # Wilder 1/14
ADX_PERIOD = 14
WARMUP_BARS = 200

# Sharpe (§5.1): 6 velas H4/día × 365 días = 2190
H4_PER_YEAR = 2190
SQRT_H4_PER_YEAR = H4_PER_YEAR ** 0.5  # ≈ 46.796

# Bootstrap CBB (§8.3, D-023)
BOOTSTRAP_BLOCK_SIZE = 20
BOOTSTRAP_BLOCK_SIZE_INFO = 10   # informativo únicamente
BOOTSTRAP_ITER = 10_000
BOOTSTRAP_SEED = 20261108
BOOTSTRAP_CONF = 0.95

# Criterios de aprobación (D-015, D-023)
MIN_TRADES = 50
MIN_SHARPE = 1.0
MAX_DD = 0.10               # 10% sobre capital_inicial
MIN_PF = 1.5
MIN_EXPECTANCY = 0.0        # estrictamente > 0 USDT


@dataclass(frozen=True)
class Config:
    name: str
    adx_threshold: float
    atr_mult: float
    is_primary: bool = False


# §6: A es primaria confirmatoria; B/C/D son exploratorias
CONFIGS = [
    Config("EXP-0001-A", adx_threshold=25.0, atr_mult=2.0, is_primary=True),
    Config("EXP-0001-B", adx_threshold=20.0, atr_mult=2.0),
    Config("EXP-0001-C", adx_threshold=25.0, atr_mult=1.5),
    Config("EXP-0001-D", adx_threshold=25.0, atr_mult=3.0),
]
