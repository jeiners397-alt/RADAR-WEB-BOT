"""Métricas calculadas solo a partir de operaciones y flujos de caja reales. Funciones puras."""
from __future__ import annotations

import math
from typing import Iterable, Sequence


def profit_factor(pnls: Iterable[float]) -> float | None:
    """None = N/A (sin pérdidas o sin operaciones). No se inventa infinito."""
    pnls = list(pnls)
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    if losses == 0:
        return None
    return wins / losses


def win_rate(pnls: Sequence[float]) -> float | None:
    if not pnls:
        return None
    return sum(1 for p in pnls if p > 0) / len(pnls) * 100


def expectancy(pnls: Sequence[float]) -> float | None:
    return (sum(pnls) / len(pnls)) if pnls else None


def max_drawdown(equity: Sequence[float]) -> dict:
    """Devuelve drawdown máximo como fracción negativa (-0.128 = -12.8%) y en valor absoluto."""
    peak = None
    mdd = 0.0
    mdd_abs = 0.0
    for e in equity:
        peak = e if peak is None or e > peak else peak
        if peak and peak > 0:
            dd = (e - peak) / peak
            if dd < mdd:
                mdd = dd
                mdd_abs = e - peak
    return {"pct": mdd * 100, "abs": mdd_abs}


def drawdown_series(equity: Sequence[float]) -> list[float]:
    out, peak = [], None
    for e in equity:
        peak = e if peak is None or e > peak else peak
        out.append(((e - peak) / peak * 100) if peak else 0.0)
    return out


def sharpe(returns: Sequence[float], periods_per_year: float = 365.0) -> float | None:
    """Sharpe sin tasa libre de riesgo sobre retornos por periodo. None si <2 muestras o varianza 0."""
    n = len(returns)
    if n < 2:
        return None
    m = sum(returns) / n
    var = sum((r - m) ** 2 for r in returns) / (n - 1)
    if var <= 0:
        return None
    return m / math.sqrt(var) * math.sqrt(periods_per_year)


def summarize_trades(pnls: Sequence[float], initial: float, equity_curve: Sequence[float] | None = None) -> dict:
    net = sum(pnls)
    curve = list(equity_curve) if equity_curve is not None else _curve(pnls, initial)
    return {
        "trades": len(pnls),
        "net_pnl": net,
        "return_pct": (net / initial * 100) if initial else None,
        "win_rate": win_rate(pnls),
        "profit_factor": profit_factor(pnls),
        "expectancy": expectancy(pnls),
        "max_drawdown_pct": max_drawdown(curve)["pct"] if curve else 0.0,
    }


def _curve(pnls: Sequence[float], initial: float) -> list[float]:
    eq, out = initial, [initial]
    for p in pnls:
        eq += p
        out.append(eq)
    return out
