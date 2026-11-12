"""Backtest determinista, sin lookahead: señal en cierre de vela i -> ejecución en la apertura de i+1."""
from __future__ import annotations

import hashlib
import json

from . import metrics
from .strategies import SIGNALS, validate_params

ENGINE_VERSION = "bt-1.0"


def dataset_hash(candles: list[dict]) -> str:
    h = hashlib.sha256()
    h.update(json.dumps([[k["t"], k["o"], k["h"], k["l"], k["c"], k["v"]] for k in candles], separators=(",", ":")).encode())
    return h.hexdigest()


def run_backtest(candles: list[dict], template: str, params: dict, *, initial: float = 100.0, fee_rate: float = 0.001,
                 slippage_bps: float = 5.0, allocation_fraction: float = 0.05, oos_fraction: float = 0.3,
                 min_notional: float = 0.0) -> dict:
    params = validate_params(template, params)
    candles = [k for k in candles if k.get("closed", True)]  # nunca usar la vela en formación
    n = len(candles)
    if n < 50:
        raise ValueError("Datos insuficientes (<50 velas cerradas)")
    sig = SIGNALS[template](candles, params)
    slip = slippage_bps / 10000
    cash, qty, entry_px, entry_fee, entry_i = initial, 0.0, 0.0, 0.0, 0
    trades, equity = [], []
    for i in range(n):
        # ejecutar en apertura de i la señal de i-1 (cerrada)
        if i > 0:
            want, have = sig[i - 1], qty > 0
            if want and not have:
                eq = cash
                notional = eq * allocation_fraction
                px = candles[i]["o"] * (1 + slip)
                if notional >= max(min_notional, 1e-9) and cash >= notional * (1 + fee_rate):
                    qty = notional / px
                    entry_fee = notional * fee_rate
                    cash -= notional + entry_fee
                    entry_px, entry_i = px, i
            elif not want and have:
                px = candles[i]["o"] * (1 - slip)
                fee = qty * px * fee_rate
                cash += qty * px - fee
                trades.append({"entry_i": entry_i, "exit_i": i, "entry_t": candles[entry_i]["t"], "exit_t": candles[i]["t"],
                               "entry": entry_px, "exit": px, "qty": qty, "fees": fee + entry_fee,
                               "pnl": (px - entry_px) * qty - fee - entry_fee})
                qty = 0.0
        equity.append(cash + qty * candles[i]["c"])
    if qty > 0:  # cierre final a mercado (marca) para contabilizar la operación abierta
        px = candles[-1]["c"] * (1 - slip)
        fee = qty * px * fee_rate
        cash += qty * px - fee
        trades.append({"entry_i": entry_i, "exit_i": n - 1, "entry_t": candles[entry_i]["t"], "exit_t": candles[-1]["t"],
                       "entry": entry_px, "exit": px, "qty": qty, "fees": fee + entry_fee,
                       "pnl": (px - entry_px) * qty - fee - entry_fee, "forced_close": True})
        equity[-1] = cash
    split = int(n * (1 - oos_fraction))
    ins = [t["pnl"] for t in trades if t["entry_i"] < split]
    oos = [t["pnl"] for t in trades if t["entry_i"] >= split]
    all_pnl = [t["pnl"] for t in trades]
    bh_qty = initial * allocation_fraction / candles[0]["o"]
    bh_curve = [initial + bh_qty * (k["c"] - candles[0]["o"]) for k in candles]
    # Buy & hold del 100% como referencia adicional
    bh_full = [initial * k["c"] / candles[0]["o"] for k in candles]
    summ = metrics.summarize_trades(all_pnl, initial, equity)
    return {
        "engine": ENGINE_VERSION, "template": template, "params": params,
        "config": {"initial": initial, "fee_rate": fee_rate, "slippage_bps": slippage_bps,
                   "allocation_fraction": allocation_fraction, "oos_fraction": oos_fraction},
        "dataset": {"hash": dataset_hash(candles), "candles": n, "from": candles[0]["t"], "to": candles[-1]["t"]},
        "metrics": summ,
        "in_sample": metrics.summarize_trades(ins, initial), "out_of_sample": metrics.summarize_trades(oos, initial),
        "oos_start_index": split,
        "benchmark": {"buy_hold_full_return_pct": (bh_full[-1] / initial - 1) * 100,
                      "buy_hold_alloc_return_pct": (bh_curve[-1] / initial - 1) * 100,
                      "max_drawdown_pct": metrics.max_drawdown(bh_full)["pct"]},
        "equity": equity[:: max(1, n // 400)], "equity_step": max(1, n // 400),
        "trades": trades[-200:], "trades_total": len(trades),
        "warnings": (["Sin operaciones: la estrategia no generó señales en este tramo"] if not trades else [])
                    + (["Muestra pequeña (<30 operaciones): métricas estadísticamente débiles"] if len(trades) < 30 else []),
    }
