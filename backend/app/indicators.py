"""Indicadores sin lookahead: el valor en i usa solo datos ≤ i. Velas: dict(t,o,h,l,c,v)."""
from __future__ import annotations

from typing import Sequence


def sma(x: Sequence[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(x)
    s = 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(x: Sequence[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(x)
    if len(x) < n:
        return out
    k = 2 / (n + 1)
    e = sum(x[:n]) / n
    out[n - 1] = e
    for i in range(n, len(x)):
        e = x[i] * k + e * (1 - k)
        out[i] = e
    return out


def rsi(x: Sequence[float], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(x)
    if len(x) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = x[i] - x[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(x)):
        d = x[i] - x[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def atr(c: Sequence[dict], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(c)
    trs = []
    for i, k in enumerate(c):
        if i == 0:
            trs.append(k["h"] - k["l"])
        else:
            pc = c[i - 1]["c"]
            trs.append(max(k["h"] - k["l"], abs(k["h"] - pc), abs(k["l"] - pc)))
    if len(c) < n:
        return out
    a = sum(trs[:n]) / n
    out[n - 1] = a
    for i in range(n, len(c)):
        a = (a * (n - 1) + trs[i]) / n
        out[i] = a
    return out


def rvol(vols: Sequence[float], n: int = 20) -> float | None:
    """Volumen relativo de la última vela vs media de las n anteriores."""
    if len(vols) <= n:
        return None
    base = sum(vols[-n - 1:-1]) / n
    return vols[-1] / base if base > 0 else None


def volume_profile(candles: Sequence[dict], bins: int = 48, value_area: float = 0.70) -> dict | None:
    """POC/VAH/VAL aproximados: el volumen de cada vela se reparte uniformemente entre sus bins [l,h].
    Metodología aproximada (granularidad de velas, no de trades)."""
    if not candles:
        return None
    lo = min(k["l"] for k in candles)
    hi = max(k["h"] for k in candles)
    if hi <= lo:
        return None
    w = (hi - lo) / bins
    vol = [0.0] * bins
    for k in candles:
        a = min(int((k["l"] - lo) / w), bins - 1)
        b = min(int((k["h"] - lo) / w), bins - 1)
        share = k["v"] / (b - a + 1)
        for j in range(a, b + 1):
            vol[j] += share
    poc = max(range(bins), key=lambda j: vol[j])
    total = sum(vol)
    acc, l, r = vol[poc], poc, poc
    while total > 0 and acc / total < value_area and (l > 0 or r < bins - 1):
        left = vol[l - 1] if l > 0 else -1
        right = vol[r + 1] if r < bins - 1 else -1
        if right >= left:
            r += 1
            acc += vol[r]
        else:
            l -= 1
            acc += vol[l]
    return {"poc": lo + (poc + 0.5) * w, "val": lo + l * w, "vah": lo + (r + 1) * w, "bins": bins,
            "method": "aprox. por velas, reparto uniforme del volumen en [low,high]"}


def regime(candles: Sequence[dict]) -> dict:
    """Clasificación simple de régimen sobre las velas dadas (por EMA55/200 y ATR%)."""
    closes = [k["c"] for k in candles]
    if len(closes) < 60:
        return {"label": "Sin datos suficientes", "code": "NA", "trend": "N/D", "volatility": "N/D"}
    e_fast = ema(closes, 21)[-1]
    e_slow = ema(closes, 55)[-1]
    a = atr(candles, 14)[-1]
    atr_pct = (a / closes[-1] * 100) if a else 0
    slope = (e_fast - e_slow) / e_slow * 100 if e_slow else 0
    if abs(slope) < 0.3:
        trend, code, label = "Neutral", "R3", "R3 – Lateral"
    elif slope > 0:
        trend, code, label = "Alcista", "R1", "R1 – Tendencia alcista"
    else:
        trend, code, label = "Bajista", "R2", "R2 – Tendencia bajista"
    vol = "Alta" if atr_pct > 3 else "Media" if atr_pct > 1 else "Baja"
    return {"label": label, "code": code, "trend": trend, "volatility": vol, "atr_pct": atr_pct, "ema_slope_pct": slope}
