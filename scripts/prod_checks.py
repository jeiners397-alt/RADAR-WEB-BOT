"""Comprobaciones de integración y seguridad contra un despliegue (p. ej. vía túnel SSH).
Uso: python scripts/prod_checks.py http://127.0.0.1:8000 <usuario> <archivo_password>
Solo opera con el usuario indicado (use uno de QA: no altera el paper de admin)."""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

import httpx

base, user, pwfile = sys.argv[1], sys.argv[2], sys.argv[3]
pw = open(pwfile, encoding="utf-8").read().strip()
res = []


def ok(name, cond, extra=""):
    res.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f" — {extra}" if extra else ""))


c = httpx.Client(base_url=base, timeout=60)
ok("sin sesión: /accounts 401", c.get("/api/v1/accounts").status_code == 401)
ok("sin sesión: /dashboard 401", c.get("/api/v1/dashboard?account_id=1").status_code == 401)
ok("admin/admin rechazado", c.post("/api/v1/auth/login", json={"username": "admin", "password": "admin"}).status_code == 401)
r = c.post("/api/v1/auth/login", json={"username": user, "password": pw})
ok("login correcto", r.status_code == 200)
csrf = r.json()["csrf"]
h = {"x-csrf-token": csrf}
ck = r.headers.get("set-cookie", "").lower()
ok("cookie HttpOnly + SameSite=Strict", "httponly" in ck and "samesite=strict" in ck)
hd = c.get("/api/v1/auth/me").headers
ok("cabeceras de seguridad", hd.get("x-frame-options") == "DENY" and "nosniff" in hd.get("x-content-type-options", "") and "default-src" in hd.get("content-security-policy", ""))
me = c.get("/api/v1/auth/me").json()
ok("flags: trading real OFF", me["flags"]["real_trading_enabled"] is False and me["flags"]["real_order_execution_enabled"] is False and me["flags"]["paper_auto_trading_enabled"] is False)
accs = c.get("/api/v1/accounts").json()
paper = [a for a in accs if a["environment"] == "paper"][0]
ok("CSRF exigido", c.post("/api/v1/paper/orders", json={"account_id": paper["id"], "symbol": "ETHUSDT", "side": "BUY", "quote_amount": 10, "confirm": True}).status_code == 403)
t = c.get("/api/v1/market/ticker?symbol=BTCUSDT").json()
ok("Binance público desde el VPS (precio real)", t.get("price", 0) > 0, f"BTCUSDT={t.get('price')} fuente={t.get('source')}")
ok("velas públicas", len(c.get("/api/v1/market/candles?symbol=ETHUSDT&interval=1h").json()["candles"]) > 100)
ins = c.get("/api/v1/market/instruments?quote=USDT&limit=5").json()
ok("catálogo de instrumentos", ins["total"] > 100, f"{ins['total']} USDT tradables")
# orden manual + cierre, comprobando ledger y aislamiento
o = c.post("/api/v1/paper/orders", headers=h, json={"account_id": paper["id"], "symbol": "ETHUSDT", "side": "BUY", "quote_amount": 17, "confirm": True, "idempotency_key": "prod-1"}).json()
ok("orden MANUAL 17 USDT llenada", o["status"] == "filled" and o["origin"] == "MANUAL" and 16.0 < o["notional"] <= 17, f"{o['status']} {o['reject_reason']} notional={o['notional']}")
o2 = c.post("/api/v1/paper/orders", headers=h, json={"account_id": paper["id"], "symbol": "ETHUSDT", "side": "BUY", "quote_amount": 17, "confirm": True, "idempotency_key": "prod-1"}).json()
ok("idempotencia: misma orden", o2["id"] == o["id"])
c.post("/api/v1/paper/orders", headers=h, json={"account_id": paper["id"], "symbol": "ETHUSDT", "side": "SELL", "confirm": True})
tr = c.get(f"/api/v1/paper/trades?account_id={paper['id']}").json()
ok("historial de operaciones cerradas", len(tr) >= 1)
s = c.get(f"/api/v1/accounts/{paper['id']}/summary").json()
ok("ledger cuadra: equity = 100 + P&L realizado", abs(s["equity"] - (100 + s["realized_pnl"])) < 1e-6, f"equity={s['equity']:.4f}")
d = c.get(f"/api/v1/trades/{tr[0]['id']}").json()
ok("trade_samples presentes", len(d["trade_samples"]) >= 2)
# algorítmico: bloqueado por flag
st = c.get(f"/api/v1/strategies?account_id={paper['id']}").json()
c.post(f"/api/v1/strategies/{st[0]['id']}/enable", headers=h, json={"account_id": paper["id"], "enabled": True})
a = c.post("/api/v1/paper/algo-orders", headers=h, json={"account_id": paper["id"], "strategy_id": st[0]["id"], "symbol": "XRPUSDT"}).json()
ok("algorítmico bloqueado con PAPER_AUTO_TRADING_ENABLED=false", a["status"] == "rejected" and "PAPER_AUTO" in a["reject_reason"])
# aislamiento: cuenta 1 (admin) no accesible
ids = {x["id"] for x in accs}
other = max(ids) + 1
other_ids = [i for i in range(1, other + 3) if i not in ids]
ok("cuentas de otros usuarios → 404", all(c.get(f"/api/v1/accounts/{i}/summary").status_code == 404 for i in other_ids[:4]), f"probadas {other_ids[:4]}")
# credenciales
SECRET = "PRODSECRET-" + str(int(time.time()))
r = c.post("/api/v1/accounts", headers=h, json={"provider": "binance", "environment": "private-readonly", "name": "qa-key", "api_key": "QAKEY1234567", "api_secret": SECRET})
ok("credencial guardada sin devolver secreto", r.status_code == 200 and SECRET not in r.text and r.json()["credential"]["trading_enabled"] is False)
ok("secreto ausente en listados/auditoría", SECRET not in c.get("/api/v1/accounts").text and SECRET not in c.get("/api/v1/audits").text)
print("SECRET_MARK", SECRET)
c.delete(f"/api/v1/accounts/{r.json()['id']}", headers=h)
# research + backtest
j = c.post("/api/v1/research/jobs", headers=h, json={"name": "prod-check", "max_symbols": 6, "timeframes": ["1h"]}).json()
for _ in range(60):
    p = c.get(f"/api/v1/research/jobs/{j['id']}").json()
    if p["progress"]["pending"] + p["progress"]["running"] == 0:
        break
    time.sleep(3)
pr = p["progress"]
ok("investigación completa y consistente", pr["total"] == 6 and pr["completed"] + pr["skipped"] + pr["failed"] == 6, str({k: pr[k] for k in ("completed", "skipped", "failed")}))
b = c.post("/api/v1/backtests", headers=h, json={"strategy_id": st[3]["id"], "symbol": "BTCUSDT", "interval": "1h", "candles": 1000}).json()
for _ in range(60):
    bt = c.get(f"/api/v1/backtests/{b['id']}").json()
    if bt["status"] in ("done", "failed"):
        break
    time.sleep(3)
ok("backtest ejecutado por el worker", bt["status"] == "done", bt.get("error", ""))
if bt["status"] == "done":
    m = bt["result"]["metrics"]
    print(f"   backtest: {m['trades']} ops, neto {m['net_pnl']:.4f}, buy&hold {bt['result']['benchmark']['buy_hold_full_return_pct']:.2f}%, hash {bt['dataset_hash'][:12]}")
w = c.get("/api/v1/research/workers").json()
ok("workers con heartbeat vivo", {x["kind"] for x in w if x["alive"]} >= {"research", "market"}, str([(x["worker_id"], round(x["age_seconds"])) for x in w]))
tm = c.get("/api/v1/telemetry/latest").json()
ok("telemetría real del VPS", tm["server"] is not None and not tm["server"]["stale"], str(tm["server"]))
print(f"\n{sum(res)}/{len(res)} OK")
sys.exit(0 if all(res) else 1)
