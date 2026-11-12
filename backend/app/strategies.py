"""Plantillas de estrategia implementadas en backend (NO se ejecuta código arbitrario del navegador).

Cada plantilla produce una señal por vela cerrada i usando solo datos <= i:
  signal[i] = 1 (entrar/mantener largo), 0 (fuera). La ejecución ocurre en la apertura de i+1 (sin lookahead).
Ninguna plantilla afirma tener ventaja: su valor solo se conoce con backtest + OOS.
"""
from __future__ import annotations

from typing import Callable

from . import indicators as ind

TEMPLATES: dict[str, dict] = {
    "liquidity_sweep": {
        "label": "Liquidity Sweep",
        "description": "Entra largo cuando la vela barre el mínimo de las últimas N velas y cierra de vuelta por encima; sale tras H velas.",
        "params": {"lookback": {"type": "int", "default": 20, "min": 5, "max": 200},
                   "hold_bars": {"type": "int", "default": 8, "min": 1, "max": 100}},
    },
    "wyckoff_spring": {
        "label": "Wyckoff Spring (aprox.)",
        "description": "Rango lateral (ATR bajo) con ruptura falsa del mínimo del rango y recuperación; sale en el máximo del rango o tras H velas.",
        "params": {"range_bars": {"type": "int", "default": 30, "min": 10, "max": 200},
                   "hold_bars": {"type": "int", "default": 12, "min": 1, "max": 100}},
    },
    "poc_recovery": {
        "label": "POC Recovery",
        "description": "Entra cuando el precio recupera (cierra por encima de) el POC móvil tras estar por debajo; sale si pierde el POC.",
        "params": {"window": {"type": "int", "default": 96, "min": 24, "max": 500}},
    },
    "volatility_breakout": {
        "label": "Volatility Breakout",
        "description": "Entra al romper el máximo (Donchian) de N velas; sale al perder el mínimo de M velas.",
        "params": {"entry_n": {"type": "int", "default": 20, "min": 5, "max": 200},
                   "exit_n": {"type": "int", "default": 10, "min": 3, "max": 100}},
    },
    "ema_cross": {
        "label": "Cruce de EMAs / Smart Money Structure (base)",
        "description": "Largo mientras EMA rápida > EMA lenta (continuación de tendencia).",
        "params": {"fast": {"type": "int", "default": 21, "min": 3, "max": 100},
                   "slow": {"type": "int", "default": 55, "min": 10, "max": 300}},
    },
    "rsi_reversion": {
        "label": "RSI Reversión",
        "description": "Entra con RSI bajo (sobreventa) y sale cuando RSI recupera el nivel de salida.",
        "params": {"period": {"type": "int", "default": 14, "min": 2, "max": 50},
                   "buy_below": {"type": "float", "default": 30, "min": 5, "max": 50},
                   "exit_above": {"type": "float", "default": 55, "min": 40, "max": 90}},
    },
}

DEFAULT_SEEDS = [  # solo plantillas con nombre; sin métricas inventadas
    ("S01", "Liquidity Sweep", "liquidity_sweep"),
    ("S02", "Wyckoff Spring", "wyckoff_spring"),
    ("S03", "POC Recovery", "poc_recovery"),
    ("S04", "Volatility Breakout", "volatility_breakout"),
    ("S05", "Smart Money Structure (EMA base)", "ema_cross"),
]


def defaults(template: str) -> dict:
    return {k: v["default"] for k, v in TEMPLATES[template]["params"].items()}


def validate_params(template: str, params: dict) -> dict:
    if template not in TEMPLATES:
        raise ValueError(f"Plantilla desconocida: {template}")
    spec = TEMPLATES[template]["params"]
    out = {}
    for k, s in spec.items():
        v = params.get(k, s["default"])
        try:
            v = int(v) if s["type"] == "int" else float(v)
        except (TypeError, ValueError):
            raise ValueError(f"Parámetro {k} inválido")
        if not (s["min"] <= v <= s["max"]):
            raise ValueError(f"Parámetro {k} fuera de rango [{s['min']}, {s['max']}]")
        out[k] = v
    extra = set(params) - set(spec)
    if extra:
        raise ValueError(f"Parámetros desconocidos: {sorted(extra)}")
    if template == "ema_cross" and out["fast"] >= out["slow"]:
        raise ValueError("fast debe ser menor que slow")
    return out


def _liquidity_sweep(c, p):
    n, hold = p["lookback"], p["hold_bars"]
    sig = [0] * len(c)
    bars_left = 0
    for i in range(n, len(c)):
        prior_low = min(k["l"] for k in c[i - n:i])
        if bars_left == 0 and c[i]["l"] < prior_low and c[i]["c"] > prior_low:
            bars_left = hold
        if bars_left > 0:
            sig[i] = 1
            bars_left -= 1
    return sig


def _wyckoff_spring(c, p):
    n, hold = p["range_bars"], p["hold_bars"]
    sig = [0] * len(c)
    left = 0
    atrs = ind.atr(c, 14)
    for i in range(n, len(c)):
        w = c[i - n:i]
        lo, hi = min(k["l"] for k in w), max(k["h"] for k in w)
        tight = atrs[i - 1] is not None and (hi - lo) < 8 * atrs[i - 1]
        if left == 0 and tight and c[i]["l"] < lo and c[i]["c"] > lo:
            left = hold
        if left > 0:
            sig[i] = 1
            left -= 1
            if c[i]["c"] >= hi:
                left = 0
    return sig


def _poc_recovery(c, p):
    w = p["window"]
    sig = [0] * len(c)
    below, holding = False, False
    for i in range(w, len(c)):
        vp = ind.volume_profile(c[i - w:i], bins=32)
        if not vp:
            continue
        poc = vp["poc"]
        if c[i]["c"] < poc:
            below, holding = True, False
        elif below and c[i]["c"] > poc:
            holding, below = True, False
        sig[i] = 1 if holding else 0
    return sig


def _vol_breakout(c, p):
    en, ex = p["entry_n"], p["exit_n"]
    sig = [0] * len(c)
    inpos = False
    for i in range(max(en, ex), len(c)):
        hi = max(k["h"] for k in c[i - en:i])
        lo = min(k["l"] for k in c[i - ex:i])
        if not inpos and c[i]["c"] > hi:
            inpos = True
        elif inpos and c[i]["c"] < lo:
            inpos = False
        sig[i] = 1 if inpos else 0
    return sig


def _ema_cross(c, p):
    cl = [k["c"] for k in c]
    f, s = ind.ema(cl, p["fast"]), ind.ema(cl, p["slow"])
    return [1 if (f[i] is not None and s[i] is not None and f[i] > s[i]) else 0 for i in range(len(c))]


def _rsi_rev(c, p):
    r = ind.rsi([k["c"] for k in c], p["period"])
    sig, inpos = [0] * len(c), False
    for i, v in enumerate(r):
        if v is None:
            continue
        if not inpos and v < p["buy_below"]:
            inpos = True
        elif inpos and v > p["exit_above"]:
            inpos = False
        sig[i] = 1 if inpos else 0
    return sig


SIGNALS: dict[str, Callable] = {
    "liquidity_sweep": _liquidity_sweep, "wyckoff_spring": _wyckoff_spring, "poc_recovery": _poc_recovery,
    "volatility_breakout": _vol_breakout, "ema_cross": _ema_cross, "rsi_reversion": _rsi_rev,
}
