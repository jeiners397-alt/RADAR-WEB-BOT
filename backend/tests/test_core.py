import threading

import pytest

from app import metrics, paper, research
from app.backtest import run_backtest
from app.config import get_settings
from app.models import Account, Position, Trade, User
from app.security import decrypt_secret, encrypt_secret, hash_password, scrub, scrub_obj
from app.sizing import SymbolFilters, algo_size, floor_to_step
from app.workers import _filters, _quote
from tests.conftest import make_candles


# ── métricas ──
def test_profit_factor_cases():
    assert metrics.profit_factor([]) is None            # cero operaciones
    assert metrics.profit_factor([5, 3]) is None        # cero pérdidas -> N/A, no infinito
    assert metrics.profit_factor([10, -5]) == pytest.approx(2.0)
    assert metrics.win_rate([]) is None
    assert metrics.win_rate([1, -1, 1, 1]) == 75.0


def test_max_drawdown():
    d = metrics.max_drawdown([100, 120, 90, 110, 80])
    assert d["pct"] == pytest.approx(-33.333, abs=0.01)
    assert metrics.max_drawdown([100, 101, 102])["pct"] == 0.0
    assert metrics.max_drawdown([])["pct"] == 0.0


def test_summarize_zero_trades():
    s = metrics.summarize_trades([], 100.0)
    assert s["trades"] == 0 and s["net_pnl"] == 0 and s["profit_factor"] is None and s["win_rate"] is None


# ── sizing 5% ──
F = SymbolFilters(step_size=0.0001, min_qty=0.0001, min_notional=5.0)


def test_algo_5pct_of_100_is_5_usdt():
    s = algo_size(100.0, 100.0, 60000.0, SymbolFilters(step_size=0.000001, min_qty=0.000001, min_notional=5.0))
    assert s.ok and s.target_notional == pytest.approx(5.0)
    assert 5.0 <= s.notional <= 5.5  # redondeo + máx. 1 step para alcanzar minNotional (≤ +10% del objetivo)


def test_algo_rejects_below_min_notional_never_upsizes():
    s = algo_size(100.0, 100.0, 60000.0, F)  # 1 step = 6 USDT: ni 0 ni 6 sirven (6 > 5.5)
    assert not s.ok and ("minNotional" in s.reason or "minQty" in s.reason)
    s2 = algo_size(100.0, 100.0, 1.0, SymbolFilters(step_size=0.1, min_qty=0.1, min_notional=10.0))
    assert not s2.ok and s2.target_notional == pytest.approx(5.0)  # no sube a 10


def test_algo_insufficient_cash():
    assert not algo_size(100.0, 3.0, 1.0, SymbolFilters(0.01, 0.01, 1.0)).ok


def test_floor_to_step_no_float_error():
    assert floor_to_step(0.30000000000000004, 0.1) == 0.3
    assert floor_to_step(1.23456, 0.01) == 1.23


# ── backtest ──
def test_backtest_deterministic_and_hash():
    c = make_candles(400)
    a = run_backtest(c, "ema_cross", {}, initial=100)
    b = run_backtest(c, "ema_cross", {}, initial=100)
    assert a == b and a["dataset"]["hash"] == b["dataset"]["hash"]


def test_backtest_no_lookahead_future_change_does_not_alter_past():
    c = make_candles(400)
    r1 = run_backtest(c, "volatility_breakout", {}, initial=100)
    c2 = [dict(k) for k in c]
    for k in c2[300:]:
        k["c"] *= 3  # alterar el futuro
        k["h"] *= 3
    r2 = run_backtest(c2, "volatility_breakout", {}, initial=100)
    early1 = [t for t in r1["trades"] if t["exit_i"] < 299 and not t.get("forced_close")]
    early2 = [t for t in r2["trades"] if t["exit_i"] < 299 and not t.get("forced_close")]
    assert early1 == early2


def test_backtest_zero_trades_and_insufficient_data():
    flat = [{"t": i, "o": 100, "h": 100, "l": 100, "c": 100, "v": 1, "closed": True} for i in range(200)]
    r = run_backtest(flat, "volatility_breakout", {})
    assert r["trades_total"] == 0 and r["metrics"]["profit_factor"] is None and r["warnings"]
    with pytest.raises(ValueError):
        run_backtest(make_candles(10), "ema_cross", {})


def test_backtest_fees_reduce_pnl_and_ignore_open_candle():
    c = make_candles(400)
    free = run_backtest(c, "ema_cross", {}, fee_rate=0, slippage_bps=0)
    paid = run_backtest(c, "ema_cross", {}, fee_rate=0.01, slippage_bps=20)
    assert paid["metrics"]["net_pnl"] < free["metrics"]["net_pnl"]
    c3 = [dict(k) for k in c]
    c3[-1]["closed"] = False
    assert run_backtest(c3, "ema_cross", {})["dataset"]["candles"] == len(c) - 1


# ── seguridad ──
def test_encryption_roundtrip_and_scrub():
    blob = encrypt_secret("MI-SECRETO-123")
    assert "MI-SECRETO" not in blob and decrypt_secret(blob) == "MI-SECRETO-123"
    assert "abc123" not in scrub("api_key=abc123 password: abc123")
    assert scrub_obj({"api_secret": "zzz", "ok": 1})["api_secret"] == "***"


# ── paper ──
def _paper(db, name="p"):
    u = User(username=f"{name}-{id(db)}", password_hash=hash_password("x" * 12))
    db.add(u)
    db.flush()
    return u, paper.ensure_default_accounts(db, u.id)["paper"]


def test_paper_starts_with_100_and_no_trades(db):
    u, acc = _paper(db)
    s = paper.summary(db, acc, _quote)
    assert s["initial_balance"] == 100.0 and s["equity"] == 100.0 and s["trades"] == 0 and s["net_pnl"] == 0


def test_manual_order_uses_user_amount_not_5pct(db):
    u, acc = _paper(db)
    o = paper.place_order(db, acc, {"symbol": "ETHUSDT", "side": "BUY", "quote_amount": 17.0}, _quote, _filters, origin="MANUAL")
    assert o.status == "filled" and o.origin == "MANUAL"
    assert 16.9 < o.notional <= 17.0
    assert o.sizing["mode"] == "manual"


def test_manual_order_validations(db):
    u, acc = _paper(db)
    r = paper.place_order(db, acc, {"symbol": "ETHUSDT", "side": "BUY", "quote_amount": 2.0}, _quote, _filters)
    assert r.status == "rejected" and "minNotional" in r.reject_reason
    r = paper.place_order(db, acc, {"symbol": "ETHUSDT", "side": "BUY", "quote_amount": 500.0}, _quote, _filters)
    assert r.status == "rejected"
    r = paper.place_order(db, acc, {"symbol": "ETHUSDT", "side": "SELL", "quantity": 1}, _quote, _filters)
    assert r.status == "rejected" and "posición" in r.reject_reason
    r = paper.place_order(db, acc, {"symbol": "NOEXISTE", "side": "BUY", "quote_amount": 10}, _quote, _filters)
    assert r.status == "rejected"


def test_algorithm_blocked_unless_auto_enabled(db):
    u, acc = _paper(db)
    assert get_settings().paper_auto_trading_enabled is False
    o = paper.place_order(db, acc, {"symbol": "XRPUSDT", "side": "BUY"}, _quote, _filters, origin="ALGORITHM", strategy_version_id=1)
    assert o.status == "rejected" and "PAPER_AUTO_TRADING_ENABLED" in o.reject_reason


def test_algorithm_5pct_when_enabled(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "paper_auto_trading_enabled", True)
    u, acc = _paper(db)
    o = paper.place_order(db, acc, {"symbol": "XRPUSDT", "side": "BUY"}, _quote, _filters, origin="ALGORITHM", strategy_version_id=7)
    assert o.status == "filled" and o.origin == "ALGORITHM" and o.strategy_version_id == 7
    assert 4.9 < o.notional <= 5.5
    assert o.sizing["fraction"] == 0.05 and o.sizing["steps"]


def test_roundtrip_pnl_ledger_consistent(db):
    u, acc = _paper(db)
    paper.place_order(db, acc, {"symbol": "ETHUSDT", "side": "BUY", "quote_amount": 50}, _quote, _filters)
    pos = db.query(Position).filter_by(account_id=acc.id).one()
    assert pos.quantity > 0
    paper.place_order(db, acc, {"symbol": "ETHUSDT", "side": "SELL"}, _quote, _filters)
    t = db.query(Trade).filter_by(account_id=acc.id).one()
    assert t.pnl < 0  # round trip al mismo precio: pierde spread+slippage+fees (real, no inventado)
    assert acc.cash == pytest.approx(100 + t.pnl, abs=1e-6)  # ledger cuadra con P&L
    assert db.query(Position).filter_by(account_id=acc.id).count() == 0


def test_idempotency_key_prevents_duplicates(db):
    u, acc = _paper(db)
    a = paper.place_order(db, acc, {"symbol": "ETHUSDT", "side": "BUY", "quote_amount": 10}, _quote, _filters, idempotency_key="k1")
    b = paper.place_order(db, acc, {"symbol": "ETHUSDT", "side": "BUY", "quote_amount": 10}, _quote, _filters, idempotency_key="k1")
    assert a.id == b.id
    assert acc.cash == pytest.approx(100 - a.notional - a.fee)


def test_kill_switch_and_real_accounts_refused(db):
    u, acc = _paper(db)
    acc.kill_switch = True
    assert paper.place_order(db, acc, {"symbol": "ETHUSDT", "side": "BUY", "quote_amount": 10}, _quote, _filters).status == "rejected"
    pub = paper.ensure_default_accounts(db, u.id)["public"]
    with pytest.raises(paper.PaperError):
        paper.place_order(db, pub, {"symbol": "ETHUSDT", "side": "BUY", "quote_amount": 10}, _quote, _filters)


def test_stop_loss_exit(db, fake):
    u, acc = _paper(db)
    paper.place_order(db, acc, {"symbol": "ETHUSDT", "side": "BUY", "quote_amount": 20, "stop_loss": 2950.0}, _quote, _filters)
    fake.prices["ETHUSDT"] = 2900.0
    closed = paper.process_exits(db, acc, _quote, _filters)
    fake.prices["ETHUSDT"] = 3000.0
    assert closed and closed[0]["hit"] == "SL"
    assert db.query(Trade).filter_by(account_id=acc.id).one().pnl < 0


def test_account_isolation_cash_and_trades(db):
    u1, a1 = _paper(db, "u1")
    u2, a2 = _paper(db, "u2")
    paper.place_order(db, a1, {"symbol": "ETHUSDT", "side": "BUY", "quote_amount": 30}, _quote, _filters)
    assert paper.summary(db, a2, _quote)["cash"] == 100.0 and len(paper.summary(db, a2, _quote)["open_positions"]) == 0
    assert a1.cash < 100


# ── investigación / workers ──
def test_research_three_workers_no_duplicates_and_consistent_counts(db):
    u = User(username="rs-user", password_hash="x")
    db.add(u)
    db.flush()
    syms = [f"S{i:02d}USDT" for i in range(30)] + ["BADUSDT", "NEWUSDT"]
    job = research.create_job(db, u.id, "t", syms, ["1h", "4h"])
    db.commit()
    jid = job.id
    assert research.job_progress(db, jid)["total"] == 64
    processed = []
    evt = threading.Event()
    prov = __import__("app.providers.binance", fromlist=["x"]).binance()

    def run(i):
        processed.append(research.worker_loop(f"w{i}", stop=evt.is_set, idle_sleep=0.01, provider=prov))
    import time as _t
    orig = _t.sleep
    _t.sleep = lambda s: orig(0.001)  # acelera el backoff simulado
    try:
        ths = [threading.Thread(target=run, args=(i,)) for i in range(3)]
        [t.start() for t in ths]
        from app.db import SessionLocal
        deadline = orig(0) or __import__("time").time() + 90
        while __import__("time").time() < deadline:
            with SessionLocal() as s2:
                pr = research.job_progress(s2, jid)
            if pr["pending"] == 0 and pr["running"] == 0:
                break
            orig(0.05)
        evt.set()
        [t.join(30) for t in ths]
    finally:
        _t.sleep = orig
    db.expire_all()
    p = research.job_progress(db, jid)
    assert p["total"] == 64 and p["pending"] == 0 and p["running"] == 0
    assert p["total"] == p["completed"] + p["skipped"] + p["failed"]
    assert p["failed"] == 2 and p["skipped"] == 2 and p["completed"] == 60  # BAD falla; NEW sin historial
    assert sum(processed) >= 64
    from app.models import JobTask
    rows = db.query(JobTask.symbol, JobTask.timeframe).filter(JobTask.job_id == jid).all()
    assert len(rows) == len(set(rows))
    assert db.get(research.ResearchJob, jid).state == "done"


def test_research_lease_recovery_after_crash(db):
    from datetime import timedelta
    from app.models import JobTask, utcnow
    u = User(username="rs2", password_hash="x")
    db.add(u)
    db.flush()
    job = research.create_job(db, u.id, "t2", ["AAAUSDT"], ["1h"])
    t = db.query(JobTask).filter_by(job_id=job.id).one()
    t.status, t.worker_id, t.lease_until = "running", "dead-worker", utcnow() - timedelta(seconds=5)
    db.commit()
    assert research.reclaim_expired(db) >= 1
    db.commit()
    db.refresh(t)
    assert t.status == "pending"


def test_paused_job_not_claimed(db):
    from app.models import JobTask
    u = User(username="rs3", password_hash="x")
    db.add(u)
    db.flush()
    job = research.create_job(db, u.id, "t3", ["PAUSEUSDT"], ["1h"])
    job.state = "paused"
    db.commit()
    got = research.claim_task(db, "w")
    assert got is None or got.job_id != job.id
