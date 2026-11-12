import pytest
from fastapi.testclient import TestClient

from app.db import session_scope
from app.main import app
from app.models import User
from app.paper import ensure_default_accounts
from app.security import hash_password

PW = "correct-horse-battery"


@pytest.fixture(scope="module")
def client():
    with session_scope() as db:
        for n in ("alice", "bob"):
            if not db.query(User).filter_by(username=n).first():
                u = User(username=n, password_hash=hash_password(PW))
                db.add(u)
                db.flush()
                ensure_default_accounts(db, u.id)
    with TestClient(app) as c:
        yield c


def login(client, user="alice", pw=PW):
    r = client.post("/api/v1/auth/login", json={"username": user, "password": pw})
    return r


@pytest.fixture()
def alice(client):
    client.cookies.clear()
    r = login(client)
    assert r.status_code == 200
    h = {"x-csrf-token": r.json()["csrf"]}
    return client, h


def test_requires_auth(client):
    client.cookies.clear()
    assert client.get("/api/v1/accounts").status_code == 401
    assert client.get("/api/v1/dashboard?account_id=1").status_code == 401


def test_bad_login_and_no_default_password(client):
    client.cookies.clear()
    assert login(client, "alice", "wrong").status_code == 401
    assert login(client, "admin", "admin").status_code == 401


def test_csrf_enforced(alice):
    c, h = alice
    acc = [a for a in c.get("/api/v1/accounts").json() if a["environment"] == "paper"][0]
    r = c.post("/api/v1/paper/orders", json={"account_id": acc["id"], "symbol": "ETHUSDT", "side": "BUY", "quote_amount": 10, "confirm": True})
    assert r.status_code == 403


def test_flags_real_trading_off(alice):
    c, h = alice
    f = c.get("/api/v1/auth/me").json()["flags"]
    assert f["real_trading_enabled"] is False and f["real_order_execution_enabled"] is False


def test_accounts_defaults_100_paper(alice):
    c, h = alice
    accs = c.get("/api/v1/accounts").json()
    paper = [a for a in accs if a["environment"] == "paper"][0]
    pub = [a for a in accs if a["environment"] == "public"][0]
    assert paper["initial_balance"] == 100.0 and pub["provider"] == "binance"
    s = c.get(f"/api/v1/accounts/{paper['id']}/summary").json()
    assert s["equity"] == 100.0 and s["trades"] == 0


def test_manual_order_flow_and_history(alice):
    c, h = alice
    paper = [a for a in c.get("/api/v1/accounts").json() if a["environment"] == "paper"][0]
    r = c.post("/api/v1/paper/orders", headers=h, json={"account_id": paper["id"], "symbol": "ETHUSDT", "side": "BUY",
                                                          "quote_amount": 17, "confirm": True, "idempotency_key": "api-1"})
    assert r.status_code == 200 and r.json()["origin"] == "MANUAL" and r.json()["status"] == "filled"
    assert c.post("/api/v1/paper/orders", headers=h, json={"account_id": paper["id"], "symbol": "ETHUSDT", "side": "BUY",
                                                             "quote_amount": 17, "confirm": False}).status_code == 400
    orders = c.get(f"/api/v1/paper/orders?account_id={paper['id']}").json()
    assert orders and orders[0]["origin"] == "MANUAL"
    pos = c.get(f"/api/v1/positions?account_id={paper['id']}").json()
    assert pos and pos[0]["symbol"] == "ETHUSDT"
    r = c.post("/api/v1/paper/orders", headers=h, json={"account_id": paper["id"], "symbol": "ETHUSDT", "side": "SELL", "confirm": True})
    assert r.json()["status"] == "filled"
    trades = c.get(f"/api/v1/paper/trades?account_id={paper['id']}").json()
    d = c.get(f"/api/v1/trades/{trades[0]['id']}").json()
    assert len(d["trade_samples"]) >= 2


def test_cross_account_isolation(client):
    client.cookies.clear()
    ra = login(client, "alice")
    ha = {"x-csrf-token": ra.json()["csrf"]}
    a_paper = [a for a in client.get("/api/v1/accounts").json() if a["environment"] == "paper"][0]
    client.cookies.clear()
    rb = login(client, "bob")
    hb = {"x-csrf-token": rb.json()["csrf"]}
    assert client.get(f"/api/v1/accounts/{a_paper['id']}/summary").status_code == 404
    assert client.get(f"/api/v1/dashboard?account_id={a_paper['id']}").status_code == 404
    assert client.get(f"/api/v1/paper/orders?account_id={a_paper['id']}").status_code == 404
    assert client.post("/api/v1/paper/orders", headers=hb, json={"account_id": a_paper["id"], "symbol": "ETHUSDT", "side": "BUY",
                                                                   "quote_amount": 10, "confirm": True}).status_code == 404
    assert client.post(f"/api/v1/risk/{a_paper['id']}/kill-switch", headers=hb, json={"active": True}).status_code == 404
    b_accs = client.get("/api/v1/accounts").json()
    assert a_paper["id"] not in [a["id"] for a in b_accs]


def test_credentials_never_returned_or_logged(alice):
    c, h = alice
    SECRET = "SUPER-SECRET-VALUE-XYZ-987"
    r = c.post("/api/v1/accounts", headers=h, json={"provider": "binance", "environment": "private-readonly", "name": "Mi Binance",
                                                      "api_key": "AKEY1234567890", "api_secret": SECRET})
    assert r.status_code == 200
    body = r.text
    assert SECRET not in body and "AKEY1234567890" not in body
    assert r.json()["credential"]["trading_enabled"] is False
    aid = r.json()["id"]
    assert SECRET not in c.get("/api/v1/accounts").text
    assert SECRET not in c.get("/api/v1/audits").text
    t = c.post(f"/api/v1/accounts/{aid}/test", headers=h).json()
    assert t["ok"] is False
    from app.db import SessionLocal
    from app.models import ProviderConnection
    with SessionLocal() as db:
        blob = db.query(ProviderConnection).order_by(ProviderConnection.id.desc()).first().secret_blob
    assert SECRET not in blob  # cifrado en BD
    assert c.delete(f"/api/v1/accounts/{aid}", headers=h).status_code == 200


def test_exness_mt5_honest_not_connected(alice):
    c, h = alice
    for prov in ("exness", "mt5"):
        r = c.post("/api/v1/accounts", headers=h, json={"provider": prov, "environment": "demo", "name": f"{prov} demo",
                                                          "login": "12345", "server": "Srv-Demo", "password": "pw-secret-1"})
        assert r.status_code == 200 and r.json()["status"] == "no_conectado"
        t = c.post(f"/api/v1/accounts/{r.json()['id']}/test", headers=h).json()
        assert t["ok"] is False
        assert "pw-secret-1" not in r.text
    provs = {p["provider"]: p for p in c.get("/api/v1/providers").json()}
    assert provs["exness"]["health"]["ok"] is False and provs["mt5"]["health"]["ok"] is False
    # el estado de cuenta no hereda datos de otra cuenta
    ex = [a for a in c.get("/api/v1/accounts").json() if a["provider"] == "exness"][0]
    s = c.get(f"/api/v1/accounts/{ex['id']}/summary").json()
    assert s["equity"] == 0.0 and s["trades"] == 0 and s["open_positions"] == []


def test_algo_endpoint_requires_enable_and_flag(alice):
    c, h = alice
    paper = [a for a in c.get("/api/v1/accounts").json() if a["environment"] == "paper"][0]
    st = c.get(f"/api/v1/strategies?account_id={paper['id']}").json()
    assert len(st) == 5 and all(s["trades"] == 0 and s["win_rate"] is None for s in st)  # sin métricas inventadas
    r = c.post("/api/v1/paper/algo-orders", headers=h, json={"account_id": paper["id"], "strategy_id": st[0]["id"], "symbol": "XRPUSDT"})
    assert r.status_code == 400  # no habilitada
    c.post(f"/api/v1/strategies/{st[0]['id']}/enable", headers=h, json={"account_id": paper["id"], "enabled": True})
    r = c.post("/api/v1/paper/algo-orders", headers=h, json={"account_id": paper["id"], "strategy_id": st[0]["id"], "symbol": "XRPUSDT"})
    assert r.status_code == 200 and r.json()["status"] == "rejected" and "PAPER_AUTO_TRADING_ENABLED" in r.json()["reject_reason"]


def test_strategy_versioning_and_validation(alice):
    c, h = alice
    st = c.get("/api/v1/strategies").json()
    s = [x for x in st if x["template"] == "ema_cross"][0]
    r = c.put(f"/api/v1/strategies/{s['id']}", headers=h, json={"params": {"fast": 9, "slow": 30}})
    assert r.status_code == 200 and r.json()["version"] == s["version"] + 1
    assert c.put(f"/api/v1/strategies/{s['id']}", headers=h, json={"params": {"fast": 50, "slow": 20}}).status_code == 400
    assert c.put(f"/api/v1/strategies/{s['id']}", headers=h, json={"params": {"evil": "__import__('os')"}}).status_code == 400


def test_dashboard_shape_and_no_fake_numbers(alice):
    c, h = alice
    paper = [a for a in c.get("/api/v1/accounts").json() if a["environment"] == "paper"][0]
    d = c.get(f"/api/v1/dashboard?account_id={paper['id']}").json()
    assert d["mode"] == "operational" and d["summary"]["initial_balance"] == 100.0
    assert d["summary"]["win_rate"] is None or d["summary"]["trades"] > 0
    assert d["research"]["job"] is None or "progress" in d["research"]["job"]
    assert {c_["provider"] for c_ in d["connectors"]} == {"binance", "exness", "mt5"}
    assert [c_ for c_ in d["connectors"] if c_["provider"] == "exness"][0]["state"] == "no conectado"
    assert d["telemetry"]["server"] is None or "cpu" in d["telemetry"]["server"]


def test_market_and_backtest_and_research_endpoints(alice):
    c, h = alice
    assert c.get("/api/v1/market/ticker?symbol=BTCUSDT").json()["price"] > 0
    assert len(c.get("/api/v1/market/candles?symbol=BTCUSDT&interval=1h").json()["candles"]) > 100
    assert c.get("/api/v1/market/candles?symbol=BTC;DROP&interval=1h").status_code == 400
    assert c.get("/api/v1/market/candles?symbol=BTCUSDT&interval=7m").status_code == 400
    ind = c.get("/api/v1/market/indicators?symbol=BTCUSDT").json()
    assert ind["rsi14"] is not None and ind["volume_profile"]["poc"] > 0
    j = c.post("/api/v1/research/jobs", headers=h, json={"name": "api-job", "max_symbols": 3, "timeframes": ["1h"]})
    assert j.status_code == 200 and j.json()["tasks"] == 3
    jid = j.json()["id"]
    p = c.post(f"/api/v1/research/jobs/{jid}/pause", headers=h).json()
    assert p["state"] == "paused"
    assert c.post(f"/api/v1/research/jobs/{jid}/resume", headers=h).json()["state"] == "running"
    assert c.post(f"/api/v1/research/jobs/{jid}/cancel", headers=h).json()["state"] == "cancelled"
    pr = c.get(f"/api/v1/research/jobs/{jid}").json()["progress"]
    assert pr["total"] == 3 and pr["total"] == pr["pending"] + pr["running"] + pr["completed"] + pr["skipped"] + pr["failed"]
    st = c.get("/api/v1/strategies").json()[0]
    b = c.post("/api/v1/backtests", headers=h, json={"strategy_id": st["id"], "symbol": "BTCUSDT", "interval": "1h", "candles": 400}).json()
    from app.db import SessionLocal
    from app.workers import run_pending_backtests
    with SessionLocal() as db:
        run_pending_backtests(db)
    r = c.get(f"/api/v1/backtests/{b['id']}").json()
    assert r["status"] == "done" and r["result"]["dataset"]["hash"] and "benchmark" in r["result"]


def test_risk_kill_switch_blocks_orders(alice):
    c, h = alice
    paper = [a for a in c.get("/api/v1/accounts").json() if a["environment"] == "paper"][0]
    assert c.post(f"/api/v1/risk/{paper['id']}/kill-switch", headers=h, json={"active": True}).json()["kill_switch"]
    r = c.post("/api/v1/paper/orders", headers=h, json={"account_id": paper["id"], "symbol": "ETHUSDT", "side": "BUY", "quote_amount": 10, "confirm": True})
    assert r.json()["status"] == "rejected" and "Kill switch" in r.json()["reject_reason"]
    c.post(f"/api/v1/risk/{paper['id']}/kill-switch", headers=h, json={"active": False})
    assert c.get(f"/api/v1/risk/{paper['id']}").json()["denials"]


def test_websocket_requires_auth(client):
    client.cookies.clear()
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/ws?account_id=1"):
            pass
