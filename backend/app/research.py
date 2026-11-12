"""Investigación con workers concurrentes: cola en BD, leases, reintentos con backoff, pausa/reanuda/cancela."""
from __future__ import annotations

import os
import socket
import time
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from . import indicators as ind
from .db import session_scope
from .models import JobTask, ResearchJob, WorkerHeartbeat, utcnow
from .providers.base import ProviderError

LEASE_SECONDS = 120
MAX_ATTEMPTS = 3
STATES = ["pending", "running", "completed", "skipped", "failed"]


def create_job(db: Session, user_id: int, name: str, symbols: list[str], timeframes: list[str], provider="binance",
               market="spot", config: dict | None = None) -> ResearchJob:
    job = ResearchJob(user_id=user_id, name=name, provider=provider, market=market,
                      config={**(config or {}), "symbols": len(symbols), "timeframes": timeframes})
    db.add(job)
    db.flush()
    # partición determinista: orden alfabético símbolo × timeframe; UNIQUE(job,symbol,tf) evita duplicados
    for sym in sorted(set(symbols)):
        for tf in timeframes:
            db.add(JobTask(job_id=job.id, symbol=sym, timeframe=tf))
    return job


def job_progress(db: Session, job_id: int) -> dict:
    rows = dict(db.execute(select(JobTask.status, func.count()).where(JobTask.job_id == job_id).group_by(JobTask.status)).all())
    counts = {s: int(rows.get(s, 0)) for s in STATES}
    total = sum(counts.values())
    done = counts["completed"] + counts["skipped"] + counts["failed"]
    last = db.scalar(select(JobTask.symbol).where(JobTask.job_id == job_id, JobTask.status.in_(["completed", "skipped", "failed"]))
                     .order_by(JobTask.updated_at.desc()).limit(1))
    return {"total": total, **counts, "processed_pct": round(done / total * 100, 1) if total else 0.0,
            "consistent": total == sum(counts.values()), "last_symbol": last}


def reclaim_expired(db: Session) -> int:
    now = utcnow()
    r = db.execute(update(JobTask).where(JobTask.status == "running", JobTask.lease_until < now)
                   .values(status="pending", worker_id=None, lease_until=None))
    return r.rowcount or 0


def claim_task(db: Session, worker_id: str) -> JobTask | None:
    """Reclamo atómico: UPDATE condicional por id; si rowcount==0 otro worker ganó y se reintenta."""
    for _ in range(10):
        cand = db.execute(
            select(JobTask.id).join(ResearchJob, ResearchJob.id == JobTask.job_id)
            .where(JobTask.status == "pending", ResearchJob.state == "running").order_by(JobTask.id).limit(1)
        ).scalar()
        if cand is None:
            return None
        res = db.execute(update(JobTask).where(JobTask.id == cand, JobTask.status == "pending").values(
            status="running", worker_id=worker_id, lease_until=utcnow() + timedelta(seconds=LEASE_SECONDS),
            attempts=JobTask.attempts + 1, updated_at=utcnow()))
        db.commit()
        if res.rowcount == 1:
            return db.get(JobTask, cand)
    return None


def analyze(candles: list[dict]) -> dict | None:
    cl = [k for k in candles if k.get("closed", True)]
    if len(cl) < 100:
        return None
    closes = [k["c"] for k in cl]
    gaps = 0
    if len(cl) > 2:
        step = cl[1]["t"] - cl[0]["t"]
        gaps = sum(1 for a, b in zip(cl, cl[1:]) if b["t"] - a["t"] > step * 1.5)
    r = ind.rsi(closes)[-1]
    a = ind.atr(cl)[-1]
    vp = ind.volume_profile(cl[-200:])
    return {"candles": len(cl), "gaps": gaps, "last_close": closes[-1], "rsi14": r,
            "atr_pct": (a / closes[-1] * 100) if a else None, "rvol20": ind.rvol([k["v"] for k in cl]),
            "poc": vp["poc"] if vp else None, "above_poc": (closes[-1] > vp["poc"]) if vp else None,
            "ret_pct": (closes[-1] / closes[0] - 1) * 100, "regime": ind.regime(cl)["code"],
            "quality": "con_gaps" if gaps else "ok"}


def process_task(db: Session, task: JobTask, provider) -> None:
    job = db.get(ResearchJob, task.job_id)
    try:
        candles = provider.get_candles(task.symbol, task.timeframe, 500, job.market)
        res = analyze(candles)
        if res is None:
            task.status, task.error = "skipped", "Historial insuficiente (<100 velas)"
        else:
            task.status, task.result, task.error = "completed", res, ""
    except ProviderError as e:
        if task.attempts < MAX_ATTEMPTS:
            task.status, task.error = "pending", f"reintento {task.attempts}: {e}"[:300]
            time.sleep(min(2 ** task.attempts, 8))  # backoff
        else:
            task.status, task.error = "failed", str(e)[:300]
    except Exception as e:  # error inesperado: no tumba el worker
        task.status, task.error = ("failed" if task.attempts >= MAX_ATTEMPTS else "pending"), f"{type(e).__name__}: {e}"[:300]
    task.worker_id, task.lease_until, task.updated_at = None, None, utcnow()
    db.commit()
    maybe_finish(db, job.id)


def maybe_finish(db: Session, job_id: int):
    p = job_progress(db, job_id)
    if p["total"] and p["pending"] == 0 and p["running"] == 0:
        job = db.get(ResearchJob, job_id)
        if job.state == "running":
            job.state, job.finished_at = "done", utcnow()
            db.commit()


def heartbeat(db: Session, worker_id: str, kind: str, info: dict):
    hb = db.get(WorkerHeartbeat, worker_id)
    if not hb:
        hb = WorkerHeartbeat(worker_id=worker_id, kind=kind, info=info)
        db.add(hb)
    hb.ts, hb.info = utcnow(), info
    db.commit()


def worker_loop(worker_id: str | None = None, stop=lambda: False, idle_sleep: float = 2.0, provider=None, max_tasks: int | None = None):
    from .providers.binance import binance
    provider = provider or binance()
    worker_id = worker_id or f"research-{socket.gethostname()}-{os.getpid()}"
    done = 0
    while not stop():
        with session_scope() as db:
            reclaim_expired(db)
            heartbeat(db, worker_id, "research", {"processed": done})
            t = claim_task(db, worker_id)
            if t is None:
                pass
            else:
                process_task(db, t, provider)
                done += 1
        if max_tasks is not None and done >= max_tasks:
            return done
        if t is None:
            if max_tasks is not None:
                return done
            time.sleep(idle_sleep)
    return done
