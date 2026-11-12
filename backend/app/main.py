"""CAPITAL RADAR PRO — API v1."""
from __future__ import annotations

import asyncio
import re
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import indicators as ind
from . import metrics, paper, research
from .config import get_settings
from .db import init_engine, session_scope
from .deps import COOKIE, current_session, current_user, get_db, owned_account
from .models import (Account, AuditEvent, BacktestRun, JobTask, Notification, Order, Position, ProviderConnection,
                     ResearchJob, RiskRule, ServerMetric, SessionRow, StrategyAccountState, StrategyDef,
                     StrategyVersion, Trade, TradeSample, User, WorkerHeartbeat, EquitySnapshot, utcnow)
from .providers.base import ProviderError
from .providers.binance import INTERVALS, binance
from .providers.gateways import ExnessAdapter, MT5Adapter
from .security import (encrypt_secret, fingerprint, mask, new_session_token, scrub, session_ttl, verify_password)
from .strategies import DEFAULT_SEEDS, TEMPLATES, defaults, validate_params
from .workers import _filters, _quote

VERSION = "1.0.0"
UI_COOKIE_MAX = 60 * 60 * 12


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine()
    yield


app = FastAPI(title="CAPITAL RADAR PRO API", version=VERSION, lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; connect-src 'self' ws: wss:; frame-ancestors 'none'"
        if not request.url.path.startswith("/api/docs") else "default-src * 'unsafe-inline' 'unsafe-eval' data:")
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ───────────────────────── salud ─────────────────────────
@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": VERSION}


@app.get("/api/v1/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(select(1))
        return {"status": "ready", "db": "ok"}
    except Exception:
        raise HTTPException(503, "db no disponible")


# ───────────────────────── auth ─────────────────────────
_login_fail_ip: dict[str, list[float]] = defaultdict(list)


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


@app.post("/api/v1/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "?"
    now = time.time()
    _login_fail_ip[ip] = [t for t in _login_fail_ip[ip] if now - t < 300]
    if len(_login_fail_ip[ip]) >= 10:
        raise HTTPException(429, "Demasiados intentos. Espera unos minutos.")
    user = db.scalar(select(User).where(User.username == body.username))
    lock = user.locked_until if user else None
    if lock and lock.tzinfo is None:
        lock = lock.replace(tzinfo=timezone.utc)
    if user and lock and lock > utcnow():
        raise HTTPException(429, "Cuenta bloqueada temporalmente")
    if not user or not verify_password(user.password_hash, body.password):
        _login_fail_ip[ip].append(now)
        if user:
            user.failed_logins += 1
            if user.failed_logins >= 5:
                user.locked_until, user.failed_logins = utcnow() + timedelta(minutes=5), 0
            paper.audit(db, "auth.login_failed", user.id)
        db.commit()
        raise HTTPException(401, "Credenciales inválidas")
    user.failed_logins, user.locked_until = 0, None
    token, tid, csrf = new_session_token()
    db.add(SessionRow(id=tid, user_id=user.id, csrf=csrf, expires_at=utcnow() + session_ttl()))
    paper.audit(db, "auth.login", user.id)
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=get_settings().cookie_secure,
                        max_age=UI_COOKIE_MAX, path="/")
    return {"username": user.username, "role": user.role, "csrf": csrf}


@app.post("/api/v1/auth/logout")
def logout(response: Response, sess=Depends(current_session), db: Session = Depends(get_db)):
    db.delete(db.get(SessionRow, sess[1].id))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/v1/auth/me")
def me(sess=Depends(current_session)):
    u, s = sess
    st = get_settings()
    return {"username": u.username, "role": u.role, "csrf": s.csrf,
            "flags": {"real_trading_enabled": False, "real_order_execution_enabled": False,
                      "paper_auto_trading_enabled": st.paper_auto_trading_enabled},
            "timezone": st.timezone_display}


# ───────────────────────── proveedores / cuentas ─────────────────────────
@app.get("/api/v1/providers")
def providers(user: User = Depends(current_user)):
    b, e, m = binance(), ExnessAdapter(), MT5Adapter()
    return [{"provider": "binance", "capabilities": b.capabilities(), "health": b.health()},
            {"provider": "exness", "capabilities": e.capabilities(), "health": e.health()},
            {"provider": "mt5", "capabilities": m.capabilities(), "health": m.health()}]


def acc_out(a: Account) -> dict:
    return {"id": a.id, "provider": a.provider, "environment": a.environment, "name": a.name, "currency": a.currency,
            "status": a.status, "initial_balance": a.initial_balance, "kill_switch": a.kill_switch,
            "settings": a.settings or {}, "has_credentials": a.connection_id is not None}


@app.get("/api/v1/accounts")
def accounts(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [acc_out(a) for a in db.scalars(select(Account).where(Account.user_id == user.id).order_by(Account.id))]


class AccountIn(BaseModel):
    provider: str
    environment: str = "demo"
    name: str = Field(max_length=80)
    api_key: str | None = Field(default=None, max_length=256)
    api_secret: str | None = Field(default=None, max_length=512)
    login: str | None = Field(default=None, max_length=64)
    server: str | None = Field(default=None, max_length=80)
    platform: str | None = Field(default=None, max_length=24)
    password: str | None = Field(default=None, max_length=256)


@app.post("/api/v1/accounts")
def add_account(body: AccountIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if body.provider not in ("binance", "exness", "mt5"):
        raise HTTPException(400, "Proveedor inválido")
    if body.environment not in ("demo", "live", "private-readonly"):
        raise HTTPException(400, "Entorno inválido")
    if body.provider == "binance":
        if not body.api_key or not body.api_secret:
            raise HTTPException(400, "API Key y Secret requeridos")
        secret_plain = body.api_key + "\n" + body.api_secret
        meta, ident, env = {}, body.api_key, "private-readonly"
        status = "guardada_sin_verificar"
    else:
        if not (body.login and body.server and body.password):
            raise HTTPException(400, "login, servidor y contraseña requeridos")
        secret_plain = body.login + "\n" + body.password
        meta, ident, env = {"login": body.login, "server": body.server, "platform": body.platform}, body.login, body.environment
        status = "no_conectado"
    conn = ProviderConnection(user_id=user.id, provider=body.provider, label=body.name, fingerprint=fingerprint(secret_plain),
                              masked=mask(ident), secret_blob=encrypt_secret(secret_plain), meta=meta, trading_enabled=False)
    db.add(conn)
    db.flush()
    acc = Account(user_id=user.id, provider=body.provider, environment=env, name=body.name, status=status,
                  connection_id=conn.id, currency="USD" if body.provider != "binance" else "USDT")
    db.add(acc)
    db.flush()
    paper.audit(db, "account.added", user.id, acc.id, provider=body.provider, env=env, fp=conn.fingerprint)
    out = acc_out(acc)
    out["credential"] = {"fingerprint": conn.fingerprint, "masked": conn.masked, "trading_enabled": False}
    return out  # el secreto no se devuelve ni se registra


@app.post("/api/v1/accounts/{aid}/test")
def test_account(aid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = owned_account(db, user, aid)
    if a.provider == "binance" and a.environment == "public":
        h = binance().health()
        return {"ok": h.get("ok", False), "detail": h}
    if a.provider == "binance" and a.environment == "paper":
        return {"ok": True, "detail": "Paper interno; no depende de una cuenta Binance externa"}
    if a.provider == "binance":
        return {"ok": False, "status": "NO_VERIFICADA",
                "detail": "La verificación de permisos de claves privadas aún no está implementada en v1 (solo se guardan cifradas)."}
    ad = ExnessAdapter() if a.provider == "exness" else MT5Adapter()
    return {"ok": False, "status": ad.capabilities()["status"], "detail": ad.health()["detail"]}


@app.delete("/api/v1/accounts/{aid}")
def delete_account(aid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = owned_account(db, user, aid)
    if a.environment in ("public", "paper"):
        raise HTTPException(400, "Las cuentas base (público/paper) no se pueden eliminar")
    if a.connection_id:
        c = db.get(ProviderConnection, a.connection_id)
        a.connection_id = None
        db.flush()
        if c:
            db.delete(c)  # revocar/borrar credencial cifrada
    paper.audit(db, "account.removed", user.id, a.id)
    db.delete(a)
    return {"ok": True}


class SettingsIn(BaseModel):
    last_market: dict | None = None
    favorites: list[str] | None = None


@app.put("/api/v1/accounts/{aid}/settings")
def account_settings(aid: int, body: SettingsIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = owned_account(db, user, aid)
    s = dict(a.settings or {})
    if body.last_market is not None:
        s["last_market"] = body.last_market
    if body.favorites is not None:
        s["favorites"] = body.favorites[:100]
    a.settings = s
    return acc_out(a)


@app.get("/api/v1/accounts/{aid}/summary")
def account_summary(aid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = owned_account(db, user, aid)
    return paper.summary(db, a, _quote)


# ───────────────────────── mercado (público) ─────────────────────────
def _market_guard(market: str):
    if market not in ("spot", "futures"):
        raise HTTPException(400, "market debe ser spot|futures")


def _wrap(fn):
    try:
        return fn()
    except ProviderError as e:
        raise HTTPException(502, str(e))


@app.get("/api/v1/market/instruments")
def instruments(market: str = "spot", q: str = "", quote: str = "", limit: int = 100, user: User = Depends(current_user)):
    _market_guard(market)
    items = _wrap(lambda: binance().list_instruments(market))
    items = [i for i in items if i["tradable"]]
    if quote:
        items = [i for i in items if i["quote"] == quote.upper()]
    if q:
        items = [i for i in items if q.upper() in i["symbol"]]
    return {"source": f"Binance {market} público", "total": len(items), "items": items[:min(limit, 500)]}


@app.get("/api/v1/market/candles")
def candles(symbol: str, interval: str = "1h", market: str = "spot", limit: int = 300, user: User = Depends(current_user)):
    _market_guard(market)
    if not re.fullmatch(r"[A-Z0-9]{3,20}", symbol.upper()):
        raise HTTPException(400, "símbolo inválido")
    if interval not in INTERVALS:
        raise HTTPException(400, "intervalo inválido")
    data = _wrap(lambda: binance().get_candles(symbol, interval, limit, market))
    return {"symbol": symbol.upper(), "interval": interval, "market": market, "source": f"Binance {market} público",
            "fetched_at": int(time.time() * 1000), "candles": data}


@app.get("/api/v1/market/ticker")
def ticker(symbol: str, market: str = "spot", user: User = Depends(current_user)):
    _market_guard(market)
    return _wrap(lambda: binance().get_ticker(symbol, market))


@app.get("/api/v1/market/tickers")
def tickers(market: str = "spot", quote: str = "USDT", sort: str = "volume", limit: int = 100, user: User = Depends(current_user)):
    _market_guard(market)
    rows = _wrap(lambda: binance().tickers_24h(market))
    rows = [r for r in rows if r["symbol"].endswith(quote.upper())]
    key = {"volume": "quote_volume", "change": "change_pct", "price": "price"}.get(sort, "quote_volume")
    rows.sort(key=lambda r: r[key], reverse=True)
    return {"source": f"Binance {market} público", "total": len(rows), "items": rows[:min(limit, 300)]}


@app.get("/api/v1/market/indicators")
def indicators_ep(symbol: str, interval: str = "1h", market: str = "spot", user: User = Depends(current_user)):
    _market_guard(market)
    c = _wrap(lambda: binance().get_candles(symbol, interval, 500, market))
    closed = [k for k in c if k["closed"]]
    cl = [k["c"] for k in closed]
    last = lambda arr: arr[-1] if arr else None  # noqa: E731
    return {"symbol": symbol.upper(), "interval": interval, "candles_used": len(closed),
            "sma": {n: last(ind.sma(cl, n)) for n in (9, 21, 55, 200)},
            "ema": {n: last(ind.ema(cl, n)) for n in (9, 21, 55, 200)},
            "rsi14": last(ind.rsi(cl)), "atr14": last(ind.atr(closed)), "rvol20": ind.rvol([k["v"] for k in closed]),
            "volume_profile": ind.volume_profile(closed[-200:]), "regime": ind.regime(closed)}


# ───────────────────────── paper ─────────────────────────
class OrderIn(BaseModel):
    account_id: int
    symbol: str
    side: str
    type: str = "market"
    limit_price: float | None = None
    quantity: float | None = Field(default=None, gt=0)
    quote_amount: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    confirm: bool = False
    idempotency_key: str | None = Field(default=None, max_length=64)
    reason: str = ""


def order_out(o: Order) -> dict:
    return {"id": o.id, "ts": o.created_at.isoformat(), "origin": o.origin, "symbol": o.symbol, "side": o.side,
            "type": o.type, "quantity": o.quantity, "notional": o.notional, "status": o.status,
            "reject_reason": o.reject_reason, "fill_price": o.fill_price, "fee": o.fee, "price_source": o.price_source,
            "reason": o.reason, "stop_loss": o.stop_loss, "take_profit": o.take_profit,
            "strategy_version_id": o.strategy_version_id, "sizing": o.sizing, "environment": o.environment}


@app.post("/api/v1/paper/orders")
def paper_order(body: OrderIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Orden MANUAL: tamaño elegido por el usuario; el 5% NO se aplica."""
    a = owned_account(db, user, body.account_id)
    if not body.confirm:
        raise HTTPException(400, "Debes confirmar la orden")
    if body.side.upper() not in ("BUY", "SELL"):
        raise HTTPException(400, "side inválido")
    try:
        o = paper.place_order(db, a, body.model_dump(), _quote, _filters, origin="MANUAL",
                              idempotency_key=body.idempotency_key, user_id=user.id)
    except paper.PaperError as e:
        raise HTTPException(400, str(e))
    return order_out(o)


@app.get("/api/v1/paper/orders")
def paper_orders(account_id: int, limit: int = 100, db: Session = Depends(get_db), user: User = Depends(current_user)):
    owned_account(db, user, account_id)
    rows = db.scalars(select(Order).where(Order.account_id == account_id).order_by(Order.id.desc()).limit(min(limit, 500)))
    return [order_out(o) for o in rows]


def trade_out(t: Trade) -> dict:
    return {"id": t.id, "symbol": t.symbol, "origin": t.origin, "quantity": t.quantity, "entry_price": t.entry_price,
            "exit_price": t.exit_price, "fees": t.fees, "pnl": t.pnl, "opened_at": t.opened_at.isoformat(),
            "closed_at": t.closed_at.isoformat(), "strategy_version_id": t.strategy_version_id}


@app.get("/api/v1/paper/trades")
def paper_trades(account_id: int, limit: int = 200, db: Session = Depends(get_db), user: User = Depends(current_user)):
    owned_account(db, user, account_id)
    rows = db.scalars(select(Trade).where(Trade.account_id == account_id).order_by(Trade.id.desc()).limit(min(limit, 1000)))
    return [trade_out(t) for t in rows]


@app.get("/api/v1/trades/{trade_id}")
def trade_detail(trade_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.get(Trade, trade_id)
    if not t:
        raise HTTPException(404, "Trade no encontrado")
    owned_account(db, user, t.account_id)
    samples = db.scalars(select(TradeSample).where(TradeSample.trade_id == t.id).order_by(TradeSample.seconds_since_entry))
    return {**trade_out(t), "trade_samples": [{"seconds_since_entry": s.seconds_since_entry, "price": s.price,
                                              "stop_loss": s.stop_loss, "take_profit": s.take_profit} for s in samples]}


@app.get("/api/v1/positions")
def positions(account_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = owned_account(db, user, account_id)
    if a.environment != "paper":
        return []
    return paper.equity_now(db, a, _quote)[2]


class ResetIn(BaseModel):
    account_id: int
    confirm: bool = False


@app.post("/api/v1/paper/reset")
def paper_reset(body: ResetIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = owned_account(db, user, body.account_id)
    if not body.confirm:
        raise HTTPException(400, "Confirma el reinicio")
    try:
        paper.reset_paper(db, a, user.id)
    except paper.PaperError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "cash": a.cash}


class AlgoIn(BaseModel):
    account_id: int
    strategy_id: int
    symbol: str
    side: str = "BUY"
    idempotency_key: str | None = Field(default=None, max_length=64)


@app.post("/api/v1/paper/algo-orders")
def algo_order(body: AlgoIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Dispara la entrada de una estrategia habilitada (origin=ALGORITHM, 5% del patrimonio). Requiere PAPER_AUTO_TRADING_ENABLED
    y estrategia habilitada explícitamente para la cuenta."""
    a = owned_account(db, user, body.account_id)
    sd = db.get(StrategyDef, body.strategy_id)
    if not sd or sd.user_id != user.id:
        raise HTTPException(404, "Estrategia no encontrada")
    st = db.scalar(select(StrategyAccountState).where(StrategyAccountState.strategy_id == sd.id, StrategyAccountState.account_id == a.id))
    if not st or not st.enabled:
        raise HTTPException(400, "Estrategia no habilitada para esta cuenta paper")
    try:
        o = paper.place_order(db, a, {"symbol": body.symbol, "side": body.side, "reason": f"Señal {sd.code} {sd.name}"},
                              _quote, _filters, origin="ALGORITHM", strategy_version_id=sd.active_version_id,
                              idempotency_key=body.idempotency_key, user_id=user.id)
    except paper.PaperError as e:
        raise HTTPException(400, str(e))
    return order_out(o)


# ───────────────────────── estrategias ─────────────────────────
def _seed_strategies(db: Session, user: User):
    if db.scalar(select(func.count()).select_from(StrategyDef).where(StrategyDef.user_id == user.id)):
        return
    for code, name, tpl in DEFAULT_SEEDS:
        sd = StrategyDef(user_id=user.id, code=code, name=name, template=tpl, notes="Plantilla de investigación (sin ventaja demostrada).")
        db.add(sd)
        db.flush()
        v = StrategyVersion(strategy_id=sd.id, version=1, params=defaults(tpl))
        db.add(v)
        db.flush()
        sd.active_version_id = v.id


def strat_out(db: Session, sd: StrategyDef, account_id: int | None = None) -> dict:
    v = db.get(StrategyVersion, sd.active_version_id) if sd.active_version_id else None
    vids = [x for x in db.scalars(select(StrategyVersion.id).where(StrategyVersion.strategy_id == sd.id))]
    q = select(Trade.pnl).where(Trade.strategy_version_id.in_(vids))
    if account_id:
        q = q.where(Trade.account_id == account_id)
    pnls = list(db.scalars(q))
    enabled = False
    if account_id:
        st = db.scalar(select(StrategyAccountState).where(StrategyAccountState.strategy_id == sd.id, StrategyAccountState.account_id == account_id))
        enabled = bool(st and st.enabled)
    return {"id": sd.id, "code": sd.code, "name": sd.name, "template": sd.template, "notes": sd.notes, "tags": sd.tags,
            "version": v.version if v else None, "version_id": sd.active_version_id, "params": v.params if v else {},
            "enabled": enabled, "trades": len(pnls), "net_pnl": sum(pnls), "win_rate": metrics.win_rate(pnls),
            "profit_factor": metrics.profit_factor(pnls)}


@app.get("/api/v1/strategies/templates")
def strategy_templates(user: User = Depends(current_user)):
    return TEMPLATES


@app.get("/api/v1/strategies")
def strategies(account_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if account_id:
        owned_account(db, user, account_id)
    _seed_strategies(db, user)
    db.flush()
    return [strat_out(db, s, account_id) for s in db.scalars(select(StrategyDef).where(StrategyDef.user_id == user.id).order_by(StrategyDef.code))]


class StrategyIn(BaseModel):
    code: str = Field(max_length=16)
    name: str = Field(max_length=80)
    template: str
    params: dict = {}
    notes: str = ""
    tags: list[str] = []


@app.post("/api/v1/strategies")
def strategy_create(body: StrategyIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        params = validate_params(body.template, body.params)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if db.scalar(select(StrategyDef).where(StrategyDef.user_id == user.id, StrategyDef.code == body.code)):
        raise HTTPException(409, "Código de estrategia ya existe")
    sd = StrategyDef(user_id=user.id, code=body.code, name=body.name, template=body.template, notes=body.notes, tags=body.tags)
    db.add(sd)
    db.flush()
    v = StrategyVersion(strategy_id=sd.id, version=1, params=params)
    db.add(v)
    db.flush()
    sd.active_version_id = v.id
    paper.audit(db, "strategy.created", user.id, code=body.code)
    return strat_out(db, sd)


class StrategyUpdate(BaseModel):
    params: dict
    notes: str | None = None
    name: str | None = None


@app.put("/api/v1/strategies/{sid}")
def strategy_update(sid: int, body: StrategyUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sd = db.get(StrategyDef, sid)
    if not sd or sd.user_id != user.id:
        raise HTTPException(404, "No encontrada")
    try:
        params = validate_params(sd.template, body.params)
    except ValueError as e:
        raise HTTPException(400, str(e))
    last = db.scalar(select(func.max(StrategyVersion.version)).where(StrategyVersion.strategy_id == sd.id)) or 0
    v = StrategyVersion(strategy_id=sd.id, version=last + 1, params=params)  # versión nueva, las previas se conservan
    db.add(v)
    db.flush()
    sd.active_version_id = v.id
    if body.notes is not None:
        sd.notes = body.notes
    if body.name:
        sd.name = body.name
    paper.audit(db, "strategy.versioned", user.id, strategy=sd.code, version=v.version)
    return strat_out(db, sd)


class EnableIn(BaseModel):
    account_id: int
    enabled: bool


@app.post("/api/v1/strategies/{sid}/enable")
def strategy_enable(sid: int, body: EnableIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sd = db.get(StrategyDef, sid)
    a = owned_account(db, user, body.account_id)
    if not sd or sd.user_id != user.id:
        raise HTTPException(404, "No encontrada")
    if a.environment != "paper":
        raise HTTPException(400, "Solo se pueden habilitar estrategias en cuentas paper")
    st = db.scalar(select(StrategyAccountState).where(StrategyAccountState.strategy_id == sd.id, StrategyAccountState.account_id == a.id))
    if not st:
        st = StrategyAccountState(strategy_id=sd.id, account_id=a.id)
        db.add(st)
    st.enabled = body.enabled
    paper.audit(db, "strategy.enabled" if body.enabled else "strategy.disabled", user.id, a.id, strategy=sd.code)
    return {"ok": True, "enabled": st.enabled, "note": "Habilitada no implica ejecución: requiere PAPER_AUTO_TRADING_ENABLED y señales."}


# ───────────────────────── backtests ─────────────────────────
class BacktestIn(BaseModel):
    strategy_id: int
    symbol: str = "BTCUSDT"
    interval: str = "1h"
    market: str = "spot"
    candles: int = Field(default=1000, ge=100, le=5000)
    initial: float = Field(default=100.0, gt=0)
    fee_rate: float = Field(default=0.001, ge=0, le=0.05)
    slippage_bps: float = Field(default=5.0, ge=0, le=500)
    allocation_fraction: float = Field(default=0.05, gt=0, le=1)
    oos_fraction: float = Field(default=0.3, ge=0.1, le=0.5)


@app.post("/api/v1/backtests")
def backtest_create(body: BacktestIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sd = db.get(StrategyDef, body.strategy_id)
    if not sd or sd.user_id != user.id:
        raise HTTPException(404, "Estrategia no encontrada")
    if body.interval not in INTERVALS:
        raise HTTPException(400, "intervalo inválido")
    cfg = body.model_dump()
    bt = BacktestRun(user_id=user.id, strategy_version_id=sd.active_version_id, config=cfg, status="queued")
    db.add(bt)
    db.flush()
    paper.audit(db, "backtest.queued", user.id, id=bt.id, strategy=sd.code)
    return {"id": bt.id, "status": bt.status}


def bt_out(bt: BacktestRun, full=True) -> dict:
    d = {"id": bt.id, "status": bt.status, "config": bt.config, "error": bt.error, "dataset_hash": bt.dataset_hash,
         "strategy_version_id": bt.strategy_version_id, "created_at": bt.created_at.isoformat()}
    if full:
        d["result"] = bt.result
    elif bt.result:
        d["summary"] = bt.result.get("metrics")
    return d


@app.get("/api/v1/backtests")
def backtests(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [bt_out(b, False) for b in db.scalars(select(BacktestRun).where(BacktestRun.user_id == user.id).order_by(BacktestRun.id.desc()).limit(50))]


@app.get("/api/v1/backtests/{bid}")
def backtest_get(bid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    bt = db.get(BacktestRun, bid)
    if not bt or bt.user_id != user.id:
        raise HTTPException(404, "No encontrado")
    return bt_out(bt)


# ───────────────────────── investigación ─────────────────────────
class ResearchIn(BaseModel):
    name: str = Field(max_length=120)
    market: str = "spot"
    quote: str = "USDT"
    max_symbols: int = Field(default=40, ge=1, le=500)
    timeframes: list[str] = ["1h"]
    symbols: list[str] | None = None


@app.post("/api/v1/research/jobs")
def research_create(body: ResearchIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _market_guard(body.market)
    if not body.timeframes or any(t not in INTERVALS for t in body.timeframes):
        raise HTTPException(400, "timeframes inválidos")
    if body.symbols:
        syms = [s.upper() for s in body.symbols][:body.max_symbols]
    else:
        rows = _wrap(lambda: binance().tickers_24h(body.market))
        tradable = {i["symbol"] for i in _wrap(lambda: binance().list_instruments(body.market)) if i["tradable"]}
        rows = [r for r in rows if r["symbol"].endswith(body.quote.upper()) and r["symbol"] in tradable]
        rows.sort(key=lambda r: r["quote_volume"], reverse=True)
        syms = [r["symbol"] for r in rows[:body.max_symbols]]
    if not syms:
        raise HTTPException(400, "El universo resultó vacío")
    job = research.create_job(db, user.id, body.name, syms, body.timeframes, "binance", body.market, {"quote": body.quote})
    paper.audit(db, "research.created", user.id, job=job.id, symbols=len(syms))
    return {"id": job.id, "tasks": len(syms) * len(body.timeframes)}


def job_out(db: Session, j: ResearchJob) -> dict:
    return {"id": j.id, "name": j.name, "provider": j.provider, "market": j.market, "state": j.state, "config": j.config,
            "created_at": j.created_at.isoformat(), "progress": research.job_progress(db, j.id)}


@app.get("/api/v1/research/jobs")
def research_list(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [job_out(db, j) for j in db.scalars(select(ResearchJob).where(ResearchJob.user_id == user.id).order_by(ResearchJob.id.desc()).limit(30))]


def _job(db, user, jid) -> ResearchJob:
    j = db.get(ResearchJob, jid)
    if not j or j.user_id != user.id:
        raise HTTPException(404, "No encontrado")
    return j


@app.get("/api/v1/research/jobs/{jid}")
def research_get(jid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    j = _job(db, user, jid)
    rows = list(db.scalars(select(JobTask).where(JobTask.job_id == jid, JobTask.status.in_(["completed", "failed", "skipped"]))
                           .order_by(JobTask.updated_at.desc()).limit(200)))
    return {**job_out(db, j), "results": [{"symbol": t.symbol, "timeframe": t.timeframe, "status": t.status, "error": t.error,
                                          "result": t.result} for t in rows]}


@app.post("/api/v1/research/jobs/{jid}/{action}")
def research_action(jid: int, action: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    j = _job(db, user, jid)
    if action == "pause" and j.state == "running":
        j.state = "paused"
    elif action == "resume" and j.state in ("paused",):
        j.state = "running"
    elif action == "cancel" and j.state in ("running", "paused"):
        j.state = "cancelled"
        for t in db.scalars(select(JobTask).where(JobTask.job_id == jid, JobTask.status == "pending")):
            t.status, t.error = "skipped", "Cancelado por el usuario"
    elif action == "retry":
        for t in db.scalars(select(JobTask).where(JobTask.job_id == jid, JobTask.status == "failed")):
            t.status, t.attempts, t.error = "pending", 0, ""
        j.state, j.finished_at = "running", None
    else:
        raise HTTPException(400, f"Acción '{action}' no válida en estado {j.state}")
    paper.audit(db, f"research.{action}", user.id, job=jid)
    return job_out(db, j)


@app.get("/api/v1/research/workers")
def research_workers(db: Session = Depends(get_db), user: User = Depends(current_user)):
    now = utcnow()
    out = []
    for w in db.scalars(select(WorkerHeartbeat)):
        ts = w.ts if w.ts.tzinfo else w.ts.replace(tzinfo=timezone.utc)
        age = (now - ts).total_seconds()
        out.append({"worker_id": w.worker_id, "kind": w.kind, "last_heartbeat": ts.isoformat(), "age_seconds": age,
                    "alive": age < 60, "info": w.info})
    return out


# ───────────────────────── analytics / telemetría ─────────────────────────
@app.get("/api/v1/analytics/strategies/{account_id}")
def analytics_strategies(account_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = owned_account(db, user, account_id)
    _seed_strategies(db, user)
    db.flush()
    out = []
    for sd in db.scalars(select(StrategyDef).where(StrategyDef.user_id == user.id).order_by(StrategyDef.code)):
        s = strat_out(db, sd, a.id)
        s["net_pnl_pct"] = (s["net_pnl"] / a.initial_balance * 100) if a.initial_balance else None
        out.append(s)
    return out


@app.get("/api/v1/analytics/equity")
def analytics_equity(account_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = owned_account(db, user, account_id)
    snaps = list(db.scalars(select(EquitySnapshot).where(EquitySnapshot.account_id == a.id).order_by(EquitySnapshot.ts)))
    pts = [{"ts": s.ts.isoformat(), "equity": s.equity} for s in snaps]
    if a.environment == "paper":
        if not pts:
            pts = [{"ts": a.created_at.isoformat(), "equity": a.initial_balance}]
        eq = paper.equity_now(db, a, _quote)[0]
        pts.append({"ts": utcnow().isoformat(), "equity": eq})
    return {"initial": a.initial_balance, "points": pts,
            "drawdown": metrics.drawdown_series([p["equity"] for p in pts])}


@app.get("/api/v1/analytics/monthly")
def analytics_monthly(account_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = owned_account(db, user, account_id)
    by: dict[str, list[float]] = defaultdict(list)
    for t in db.scalars(select(Trade).where(Trade.account_id == a.id)):
        by[t.closed_at.strftime("%Y-%m")].append(t.pnl)
    rows = [{"month": m, "pnl": sum(v), "return_pct": (sum(v) / a.initial_balance * 100) if a.initial_balance else None, "trades": len(v)}
            for m, v in sorted(by.items(), reverse=True)]
    return {"rows": rows, "total_trades": sum(r["trades"] for r in rows), "total_pnl": sum(r["pnl"] for r in rows)}


@app.get("/api/v1/telemetry/latest")
def telemetry_latest(db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = db.scalar(select(ServerMetric).order_by(ServerMetric.id.desc()).limit(1))
    now = utcnow()
    hb = [{"worker_id": w.worker_id, "kind": w.kind, "age_seconds": (now - (w.ts if w.ts.tzinfo else w.ts.replace(tzinfo=timezone.utc))).total_seconds()}
          for w in db.scalars(select(WorkerHeartbeat))]
    b = binance()
    pend = db.scalar(select(func.count()).select_from(JobTask).where(JobTask.status == "pending")) or 0
    if m:
        ts = m.ts if m.ts.tzinfo else m.ts.replace(tzinfo=timezone.utc)
        server = {"cpu": m.cpu, "ram": m.ram, "disk": m.disk, "ts": ts.isoformat(), "stale": (now - ts).total_seconds() > 90}
    else:
        server = None  # el market worker aún no reportó: no se inventan valores
    return {"server": server, "api_latency_ms": b.last_latency_ms, "db_status": "ok", "workers": hb, "queue_pending": pend,
            "binance_last_ok": b.last_ok_at, "binance_used_weight_1m": b.used_weight}


# ───────────────────────── riesgo ─────────────────────────
class RiskIn(BaseModel):
    max_open_positions: int = Field(ge=1, le=50)
    max_total_exposure_pct: float = Field(gt=0, le=100)
    max_daily_loss_pct: float = Field(gt=0, le=100)
    max_order_notional: float | None = Field(default=None, gt=0)


@app.get("/api/v1/risk/{account_id}")
def risk_get(account_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = owned_account(db, user, account_id)
    r = paper._risk(db, a)
    denials = [order_out(o) for o in db.scalars(select(Order).where(Order.account_id == a.id, Order.status == "rejected").order_by(Order.id.desc()).limit(30))]
    exposure = None
    if a.environment == "paper":
        eq, pv, _ = paper.equity_now(db, a, _quote)
        exposure = (pv / eq * 100) if eq else 0
    return {"account_id": a.id, "kill_switch": a.kill_switch, "max_open_positions": r.max_open_positions,
            "max_total_exposure_pct": r.max_total_exposure_pct, "max_daily_loss_pct": r.max_daily_loss_pct,
            "max_order_notional": r.max_order_notional, "current_exposure_pct": exposure, "denials": denials}


@app.put("/api/v1/risk/{account_id}")
def risk_put(account_id: int, body: RiskIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = owned_account(db, user, account_id)
    r = paper._risk(db, a)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    paper.audit(db, "risk.updated", user.id, a.id, **body.model_dump())
    return {"ok": True}


class KillIn(BaseModel):
    active: bool


@app.post("/api/v1/risk/{account_id}/kill-switch")
def kill_switch(account_id: int, body: KillIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = owned_account(db, user, account_id)
    a.kill_switch = body.active
    paper.audit(db, "risk.kill_switch", user.id, a.id, active=body.active)
    return {"ok": True, "kill_switch": a.kill_switch}


# ───────────────────────── auditoría / notificaciones ─────────────────────────
@app.get("/api/v1/audits")
def audits(limit: int = 200, action: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(AuditEvent).where((AuditEvent.user_id == user.id) | (AuditEvent.user_id.is_(None))).order_by(AuditEvent.id.desc()).limit(min(limit, 1000))
    if action:
        q = q.where(AuditEvent.action.like(action + "%"))
    return [{"id": e.id, "ts": e.ts.isoformat(), "action": e.action, "account_id": e.account_id, "detail": e.detail} for e in db.scalars(q)]


@app.get("/api/v1/notifications")
def notifications(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [{"id": n.id, "level": n.level, "text": n.text, "ts": n.ts.isoformat(), "read": n.read}
            for n in db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(30))]


@app.get("/api/v1/reports/export")
def export_report(account_id: int, kind: str = "trades", fmt: str = "csv", db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = owned_account(db, user, account_id)
    if kind == "trades":
        rows = [trade_out(t) for t in db.scalars(select(Trade).where(Trade.account_id == a.id).order_by(Trade.id))]
    elif kind == "orders":
        rows = [order_out(o) | {"sizing": ""} for o in db.scalars(select(Order).where(Order.account_id == a.id).order_by(Order.id))]
    else:
        raise HTTPException(400, "kind inválido")
    if fmt == "json":
        return rows
    import csv, io
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={kind}_{a.id}.csv"})


# ───────────────────────── dashboard ─────────────────────────
@app.get("/api/v1/dashboard")
def dashboard(account_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = owned_account(db, user, account_id)
    _seed_strategies(db, user)
    db.flush()
    summ = paper.summary(db, a, _quote)
    job = db.scalar(select(ResearchJob).where(ResearchJob.user_id == user.id).order_by(ResearchJob.id.desc()).limit(1))
    prog = research.job_progress(db, job.id) if job else None
    elapsed = None
    if job:
        ct = job.created_at if job.created_at.tzinfo else job.created_at.replace(tzinfo=timezone.utc)
        end = job.finished_at or utcnow()
        end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
        elapsed = int((end - ct).total_seconds())
    activity = [{"ts": e.ts.isoformat(), "text": e.action.replace(".", " · ") + (f" {e.detail.get('symbol')}" if e.detail.get("symbol") else "")}
                for e in db.scalars(select(AuditEvent).where((AuditEvent.user_id == user.id) | (AuditEvent.account_id == a.id)).order_by(AuditEvent.id.desc()).limit(8))]
    regime = None
    try:
        c = [k for k in binance().get_candles("BTCUSDT", "1h", 300) if k["closed"]]
        regime = ind.regime(c)
    except Exception:
        regime = None
    now = utcnow()
    workers = []
    for w in db.scalars(select(WorkerHeartbeat)):
        ts = w.ts if w.ts.tzinfo else w.ts.replace(tzinfo=timezone.utc)
        workers.append({"worker_id": w.worker_id, "kind": w.kind, "alive": (now - ts).total_seconds() < 60})
    bh = binance().health()
    actions = []
    if prog and prog["pending"] + prog["running"] > 0:
        actions.append({"text": f"Completar procesamiento ({prog['pending'] + prog['running']})", "done": False})
    elif prog and prog["total"]:
        actions.append({"text": "Procesamiento de investigación completado", "done": True})
    else:
        actions.append({"text": "Crear una investigación R2.0", "done": False})
    actions += [{"text": "Validación estadística (backtest OOS)", "done": bool(db.scalar(select(func.count()).select_from(BacktestRun).where(BacktestRun.user_id == user.id, BacktestRun.status == "done")))},
                {"text": "Habilitar una estrategia en paper", "done": bool(db.scalar(select(func.count()).select_from(StrategyAccountState).where(StrategyAccountState.account_id == a.id, StrategyAccountState.enabled == True)))},  # noqa: E712
                {"text": "Auditoría de resultados", "done": False}]
    tm = telemetry_latest(db, user)
    return {
        "account": acc_out(a), "mode": "operational", "summary": summ,
        "research": {"job": job_out(db, job) if job else None, "elapsed_seconds": elapsed},
        "universe": prog, "activity": activity, "regime": regime, "next_actions": actions,
        "strategies": analytics_strategies(a.id, db, user)[:5], "strategies_total": db.scalar(select(func.count()).select_from(StrategyDef).where(StrategyDef.user_id == user.id)),
        "connectors": [{"provider": "binance", "label": "Binance", "subtitle": "Spot · Futuros (público)", "state": "conectado" if bh.get("ok") else "sin conexión", "latency_ms": bh.get("latency_ms")},
                       {"provider": "exness", "label": "Exness", "subtitle": "Forex · CFDs", "state": "no conectado"},
                       {"provider": "mt5", "label": "MetaTrader 5", "subtitle": "Forex · Índices · Cripto", "state": "no conectado"}],
        "bots": {"workers": workers, "paper_auto_enabled": get_settings().paper_auto_trading_enabled,
                 "strategies_enabled": db.scalar(select(func.count()).select_from(StrategyAccountState).where(StrategyAccountState.account_id == a.id, StrategyAccountState.enabled == True))},  # noqa: E712
        "monthly": analytics_monthly(a.id, db, user), "telemetry": tm,
        "as_of": now.isoformat(),
    }


# ───────────────────────── WebSocket (snapshot + heartbeat con secuencia) ─────────────────────────
@app.websocket("/api/v1/ws")
async def ws(websocket: WebSocket, account_id: int):
    tok = websocket.cookies.get(COOKIE)
    from .security import token_id
    with session_scope() as db:
        row = db.get(SessionRow, token_id(tok)) if tok else None
        acc = db.get(Account, account_id)
        ok = bool(row and acc and acc.user_id == row.user_id)
        exp = row.expires_at if row else None
    if not ok:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    seq = 0
    try:
        while True:
            seq += 1
            if exp and (exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)) < utcnow():
                await websocket.close(code=4401)
                return

            def snap():
                with session_scope() as db:
                    a = db.get(Account, account_id)
                    s = paper.summary(db, a, _quote)
                    return {"equity": s["equity"], "net_pnl": s["net_pnl"], "cash": s["cash"], "open": len(s["open_positions"])}
            try:
                data = await asyncio.to_thread(snap)
            except Exception:
                data = None
            await websocket.send_json({"seq": seq, "account_id": account_id, "type": "snapshot", "ts": time.time(), "data": data})
            await asyncio.sleep(5)
    except (WebSocketDisconnect, RuntimeError):
        return


# ───────────────────────── frontend estático (si fue compilado) ─────────────────────────
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    from fastapi.responses import FileResponse

    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = _dist / path
        if path and f.is_file() and _dist in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(_dist / "index.html")
