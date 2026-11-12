"""Entradas de worker: `python -m app.workers research` | `market`.
research: procesa tareas de investigación (concurrencia = RESEARCH_WORKERS hilos; I/O bound).
market:   telemetría del servidor, equity snapshots, salidas SL/TP paper, ejecución de backtests en cola.
"""
from __future__ import annotations

import signal
import sys
import threading
import time

import psutil
from sqlalchemy import select

from . import paper
from .backtest import run_backtest
from .config import get_settings
from .db import init_engine, session_scope
from .models import Account, BacktestRun, ServerMetric, StrategyVersion, StrategyDef
from .providers.binance import binance
from .research import heartbeat, worker_loop

_stop = threading.Event()


def _quote(sym, market):
    t = binance().get_ticker(sym, market)
    return {"bid": t["bid"], "ask": t["ask"], "price": t["price"], "source": t["source"]}


def _filters(sym, market):
    return binance().symbol_filters(sym, market)


def fetch_history(symbol: str, interval: str, total: int, market: str = "spot") -> list[dict]:
    """Descarga paginada hacia atrás (máx. 5000 velas)."""
    total = min(total, 5000)
    out: list[dict] = []
    end = None
    while len(out) < total:
        batch = binance().get_candles(symbol, interval, min(1000, total - len(out)), market, end_time=end)
        if not batch:
            break
        out = batch + out
        end = batch[0]["t"] - 1
        if len(batch) < 2:
            break
    seen, uniq = set(), []
    for k in out:
        if k["t"] not in seen:
            seen.add(k["t"])
            uniq.append(k)
    return uniq


def run_pending_backtests(db) -> int:
    n = 0
    for bt in list(db.scalars(select(BacktestRun).where(BacktestRun.status == "queued").limit(3))):
        bt.status = "running"
        db.commit()
        try:
            sv = db.get(StrategyVersion, bt.strategy_version_id)
            sd = db.get(StrategyDef, sv.strategy_id)
            c = bt.config
            candles = fetch_history(c["symbol"], c["interval"], c.get("candles", 1000), c.get("market", "spot"))
            flt = binance().symbol_filters(c["symbol"], c.get("market", "spot"))
            res = run_backtest(candles, sd.template, sv.params, initial=c.get("initial", 100.0),
                               fee_rate=c.get("fee_rate", 0.001), slippage_bps=c.get("slippage_bps", 5.0),
                               allocation_fraction=c.get("allocation_fraction", 0.05),
                               oos_fraction=c.get("oos_fraction", 0.3), min_notional=flt.min_notional)
            res["symbol"], res["interval"] = c["symbol"], c["interval"]
            bt.result, bt.dataset_hash, bt.status = res, res["dataset"]["hash"], "done"
        except Exception as e:
            bt.status, bt.error = "failed", f"{type(e).__name__}: {e}"[:300]
        db.commit()
        n += 1
    return n


def market_loop(stop=lambda: False, interval: float = 15.0):
    s = get_settings()
    wid = "market-1"
    psutil.cpu_percent(None)
    last_snap = 0.0
    while not stop():
        try:
            with session_scope() as db:
                cpu = psutil.cpu_percent(None)
                ram = psutil.virtual_memory().percent
                disk = psutil.disk_usage(str(s.data_path)).percent
                lat = binance().last_latency_ms
                db.add(ServerMetric(cpu=cpu, ram=ram, disk=disk, api_latency_ms=lat))
                heartbeat(db, wid, "market", {"cpu": cpu, "ram": ram})
                for acc in db.scalars(select(Account).where(Account.environment == "paper")):
                    try:
                        paper.process_exits(db, acc, _quote, _filters)
                        if time.time() - last_snap > 300:
                            paper.snapshot(db, acc, _quote)
                    except Exception:
                        pass
                if time.time() - last_snap > 300:
                    last_snap = time.time()
                run_pending_backtests(db)
        except Exception as e:  # nunca morir por un error transitorio
            print(f"[market] error: {type(e).__name__}", flush=True)
        time.sleep(interval)


def main():
    init_engine()
    kind = sys.argv[1] if len(sys.argv) > 1 else "research"
    signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    s = get_settings()
    if kind == "research":
        threads = [threading.Thread(target=worker_loop, kwargs={"worker_id": f"research-{i + 1}", "stop": _stop.is_set}, daemon=True)
                   for i in range(max(1, s.research_workers))]
        for t in threads:
            t.start()
        while not _stop.is_set():
            time.sleep(1)
    elif kind == "market":
        market_loop(_stop.is_set)
    else:
        raise SystemExit("uso: python -m app.workers research|market")


if __name__ == "__main__":
    main()
