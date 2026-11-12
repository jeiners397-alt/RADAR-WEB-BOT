"""Motor Paper Trading con ledger consistente. Solo spot largo (sin apalancamiento, sin cortos).

- MANUAL: cantidad/monto elegido por el usuario. NO aplica el 5%.
- ALGORITHM: exposición objetivo = fraction (5%) del patrimonio, ver sizing.py.
- Saldo reservado atómicamente: la fila de cuenta se bloquea (SELECT ... FOR UPDATE en PostgreSQL; en SQLite
  la escritura es serializada por la propia base) y todo ocurre en una transacción.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import metrics
from .config import get_settings
from .models import (Account, AuditEvent, CashMovement, EquitySnapshot, Order, Position, RiskRule, Trade, TradeSample,
                     utcnow)
from .sizing import SymbolFilters, algo_size, floor_to_step

QuoteFn = Callable[[str, str], dict]       # (symbol, market) -> {bid, ask, price, source}
FiltersFn = Callable[[str, str], SymbolFilters]


class PaperError(Exception):
    pass


def audit(db: Session, action: str, user_id=None, account_id=None, **detail):
    from .security import scrub_obj
    db.add(AuditEvent(action=action, user_id=user_id, account_id=account_id, detail=scrub_obj(detail)))


def ensure_default_accounts(db: Session, user_id: int) -> dict:
    s = get_settings()
    pub = db.scalar(select(Account).where(Account.user_id == user_id, Account.provider == "binance",
                                          Account.environment == "public"))
    if not pub:
        pub = Account(user_id=user_id, provider="binance", environment="public", name="Binance Público / Research",
                      currency="USDT", status="connected", initial_balance=0, cash=0)
        db.add(pub)
    paper = db.scalar(select(Account).where(Account.user_id == user_id, Account.provider == "binance",
                                            Account.environment == "paper"))
    if not paper:
        paper = Account(user_id=user_id, provider="binance", environment="paper", name="Binance Paper (USDT)",
                        currency="USDT", status="connected", initial_balance=s.paper_initial_usdt,
                        cash=s.paper_initial_usdt)
        db.add(paper)
        db.flush()
        db.add(CashMovement(account_id=paper.id, kind="initial", amount=s.paper_initial_usdt,
                            balance_after=s.paper_initial_usdt, ref="capital inicial virtual"))
        db.add(RiskRule(account_id=paper.id))
        audit(db, "paper.account_created", user_id, paper.id, initial=s.paper_initial_usdt)
    db.flush()
    return {"public": pub, "paper": paper}


def _risk(db: Session, account: Account) -> RiskRule:
    r = db.scalar(select(RiskRule).where(RiskRule.account_id == account.id))
    if not r:
        r = RiskRule(account_id=account.id)
        db.add(r)
        db.flush()
    return r


def positions_of(db: Session, account_id: int) -> list[Position]:
    return list(db.scalars(select(Position).where(Position.account_id == account_id)))


def equity_now(db: Session, account: Account, quote: QuoteFn) -> tuple[float, float, list[dict]]:
    """(equity, valor posiciones, detalle) — marca a mercado con bid."""
    total, rows = 0.0, []
    for p in positions_of(db, account.id):
        try:
            q = quote(p.symbol, p.market)
            mark, src = q["bid"] or q["price"], q.get("source", "")
        except Exception:
            mark, src = p.avg_price, "sin precio (costo)"
        v = p.quantity * mark
        total += v
        rows.append({"symbol": p.symbol, "market": p.market, "quantity": p.quantity, "avg_price": p.avg_price,
                     "mark": mark, "value": v, "unrealized": (mark - p.avg_price) * p.quantity,
                     "origin": p.origin, "stop_loss": p.stop_loss, "take_profit": p.take_profit,
                     "opened_at": p.opened_at.isoformat(), "price_source": src})
    return account.cash + total, total, rows


def _reject(db, account, req, origin, reason, idem=None, sizing=None, sv=None) -> Order:
    o = Order(account_id=account.id, provider=account.provider, environment=account.environment, origin=origin,
              strategy_version_id=sv, symbol=req["symbol"], market=req.get("market", "spot"), side=req["side"],
              type=req.get("type", "market"), status="rejected", reject_reason=reason[:200],
              reason=req.get("reason", "")[:200], idempotency_key=idem, sizing=sizing or {})
    db.add(o)
    audit(db, "paper.order_rejected", account_id=account.id, origin=origin, symbol=req["symbol"], reason=reason)
    db.flush()
    return o


def place_order(db: Session, account: Account, req: dict, quote: QuoteFn, filters_fn: FiltersFn,
                origin: str = "MANUAL", strategy_version_id: int | None = None, idempotency_key: str | None = None,
                user_id: int | None = None) -> Order:
    """req: symbol, market, side(BUY/SELL), type(market/limit), limit_price, quantity | quote_amount, stop_loss, take_profit."""
    s = get_settings()
    if account.environment != "paper" or account.provider != "binance":
        raise PaperError("Solo se permite Paper Trading en cuentas Binance paper (no hay ejecución real).")
    if origin not in ("MANUAL", "ALGORITHM"):
        raise PaperError("origin inválido")
    req = {**req, "symbol": req["symbol"].upper(), "side": req["side"].upper(), "market": "spot"}
    if idempotency_key:
        prev = db.scalar(select(Order).where(Order.account_id == account.id, Order.idempotency_key == idempotency_key))
        if prev:
            return prev
    # bloquea la fila de cuenta (reserva atómica de saldo)
    account = db.scalar(select(Account).where(Account.id == account.id).with_for_update())
    sym, side = req["symbol"], req["side"]
    if account.kill_switch:
        return _reject(db, account, req, origin, "Kill switch activo en esta cuenta", idempotency_key, sv=strategy_version_id)
    if origin == "ALGORITHM" and not s.paper_auto_trading_enabled:
        return _reject(db, account, req, origin, "PAPER_AUTO_TRADING_ENABLED=false (automatización paper desactivada)",
                       idempotency_key, sv=strategy_version_id)
    try:
        q = quote(sym, "spot")
        flt = filters_fn(sym, "spot")
    except Exception as e:  # sin feed válido: no se simula
        return _reject(db, account, req, origin, f"Sin precio/filtros verificables: {type(e).__name__}",
                       idempotency_key, sv=strategy_version_id)
    slip = s.paper_slippage_bps / 10000
    fee_rate = s.paper_fee_rate
    ref_px = q["ask"] if side == "BUY" else q["bid"]
    if req.get("type", "market") == "limit":
        lp = req.get("limit_price")
        if not lp or lp <= 0:
            return _reject(db, account, req, origin, "Orden límite sin precio", idempotency_key, sv=strategy_version_id)
        marketable = (side == "BUY" and lp >= q["ask"]) or (side == "SELL" and lp <= q["bid"])
        if not marketable:
            return _reject(db, account, req, origin,
                           "Límite no ejecutable ahora: el paper v1 solo llena órdenes inmediatamente ejecutables",
                           idempotency_key, sv=strategy_version_id)
    fill = ref_px * (1 + slip) if side == "BUY" else ref_px * (1 - slip)
    equity, _, _ = equity_now(db, account, quote)
    sizing: dict = {}

    if side == "BUY":
        if origin == "ALGORITHM":
            sz = algo_size(equity, account.cash, fill, flt, s.algo_allocation_fraction, fee_rate)
            sizing = sz.asdict()
            if not sz.ok:
                return _reject(db, account, req, origin, sz.reason, idempotency_key, sizing, strategy_version_id)
            qty = sz.quantity
        else:
            if req.get("quantity"):
                qty = floor_to_step(float(req["quantity"]), flt.step_size)
            elif req.get("quote_amount"):
                qty = floor_to_step(float(req["quote_amount"]) / fill, flt.step_size)
            else:
                return _reject(db, account, req, origin, "Indica cantidad o monto", idempotency_key, sv=strategy_version_id)
            sizing = {"mode": "manual", "note": "Tamaño elegido por el usuario; no se aplica el 5%"}
        notional = qty * fill
        fee = notional * fee_rate
        if qty <= 0 or qty < flt.min_qty:
            return _reject(db, account, req, origin, f"Cantidad {qty} < minQty {flt.min_qty}", idempotency_key, sizing, strategy_version_id)
        if notional < flt.min_notional:
            return _reject(db, account, req, origin, f"Nocional {notional:.4f} < minNotional {flt.min_notional} (no se ajusta solo)",
                           idempotency_key, sizing, strategy_version_id)
        # Guardas de riesgo (server-side)
        rr = _risk(db, account)
        if notional + fee > account.cash + 1e-9:
            return _reject(db, account, req, origin, f"Fondos insuficientes: requiere {notional + fee:.4f}, disponible {account.cash:.4f}",
                           idempotency_key, sizing, strategy_version_id)
        if rr.max_order_notional and notional > rr.max_order_notional:
            return _reject(db, account, req, origin, f"Excede nocional máximo por orden ({rr.max_order_notional})", idempotency_key, sizing, strategy_version_id)
        open_pos = positions_of(db, account.id)
        if not any(p.symbol == sym for p in open_pos) and len(open_pos) >= rr.max_open_positions:
            return _reject(db, account, req, origin, f"Máximo de posiciones abiertas ({rr.max_open_positions})", idempotency_key, sizing, strategy_version_id)
        exposure = equity - account.cash + notional
        if equity > 0 and exposure / equity * 100 > rr.max_total_exposure_pct:
            return _reject(db, account, req, origin, f"Excede exposición total máxima ({rr.max_total_exposure_pct}%)", idempotency_key, sizing, strategy_version_id)
        start_day = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        day_pnl = db.scalar(select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(Trade.account_id == account.id, Trade.closed_at >= start_day)) or 0.0
        if equity > 0 and -day_pnl / equity * 100 >= rr.max_daily_loss_pct:
            return _reject(db, account, req, origin, "Límite de pérdida diaria alcanzado", idempotency_key, sizing, strategy_version_id)
        # ejecutar
        account.cash -= notional + fee
        db.add(CashMovement(account_id=account.id, kind="fill_buy", amount=-(notional + fee), balance_after=account.cash, ref=sym))
        pos = db.scalar(select(Position).where(Position.account_id == account.id, Position.symbol == sym))
        if pos:
            tot = pos.quantity + qty
            pos.avg_price = (pos.avg_price * pos.quantity + fill * qty) / tot
            pos.quantity = tot
            pos.entry_fee += fee
            if req.get("stop_loss"):
                pos.stop_loss = req["stop_loss"]
            if req.get("take_profit"):
                pos.take_profit = req["take_profit"]
        else:
            db.add(Position(account_id=account.id, symbol=sym, market="spot", quantity=qty, avg_price=fill, origin=origin,
                            strategy_version_id=strategy_version_id, stop_loss=req.get("stop_loss"),
                            take_profit=req.get("take_profit"), entry_fee=fee))
    else:  # SELL (cierra/reduce posición larga)
        pos = db.scalar(select(Position).where(Position.account_id == account.id, Position.symbol == sym))
        if not pos:
            return _reject(db, account, req, origin, "No hay posición abierta (sin cortos en spot paper)", idempotency_key, sv=strategy_version_id)
        qty = floor_to_step(float(req.get("quantity") or pos.quantity), flt.step_size)
        if req.get("quantity") is None or qty > pos.quantity:
            qty = pos.quantity
        notional = qty * fill
        fee = notional * fee_rate
        if qty <= 0:
            return _reject(db, account, req, origin, "Cantidad inválida", idempotency_key, sv=strategy_version_id)
        sizing = {"mode": "close"}
        _close(db, account, pos, qty, fill, fee)
    o = Order(account_id=account.id, provider=account.provider, environment=account.environment, origin=origin,
              strategy_version_id=strategy_version_id, symbol=sym, market="spot", side=side,
              type=req.get("type", "market"), limit_price=req.get("limit_price"), quantity=qty, notional=notional,
              stop_loss=req.get("stop_loss"), take_profit=req.get("take_profit"), status="filled", fill_price=fill,
              fee=fee, price_source=q.get("source", ""), reason=(req.get("reason") or "")[:200],
              idempotency_key=idempotency_key, sizing=sizing)
    db.add(o)
    audit(db, "paper.order_filled", user_id, account.id, origin=origin, symbol=sym, side=side, qty=qty, price=fill, fee=fee)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise PaperError("Orden duplicada (idempotency key)")
    snapshot(db, account, quote)
    return o


def _close(db: Session, account: Account, pos: Position, qty: float, price: float, fee: float, ts=None):
    ts = ts or utcnow()
    proceeds = qty * price - fee
    frac = qty / pos.quantity if pos.quantity else 1.0
    entry_fee_part = pos.entry_fee * frac
    pnl = (price - pos.avg_price) * qty - fee - entry_fee_part
    account.cash += proceeds
    db.add(CashMovement(account_id=account.id, kind="fill_sell", amount=proceeds, balance_after=account.cash, ref=pos.symbol))
    t = Trade(account_id=account.id, symbol=pos.symbol, origin=pos.origin, strategy_version_id=pos.strategy_version_id,
              quantity=qty, entry_price=pos.avg_price, exit_price=price, fees=fee + entry_fee_part, pnl=pnl,
              opened_at=pos.opened_at, closed_at=ts)
    db.add(t)
    db.flush()
    opened = pos.opened_at if pos.opened_at.tzinfo else pos.opened_at.replace(tzinfo=timezone.utc)
    secs = max(int((ts - opened).total_seconds()), 0)
    db.add(TradeSample(trade_id=t.id, seconds_since_entry=0, price=pos.avg_price, stop_loss=pos.stop_loss, take_profit=pos.take_profit))
    db.add(TradeSample(trade_id=t.id, seconds_since_entry=secs, price=price, stop_loss=pos.stop_loss, take_profit=pos.take_profit))
    pos.quantity -= qty
    pos.entry_fee -= entry_fee_part
    if pos.quantity <= 1e-12:
        db.delete(pos)
    return t


def process_exits(db: Session, account: Account, quote: QuoteFn, filters_fn: FiltersFn) -> list[dict]:
    """Cierra posiciones cuyo SL/TP fue alcanzado por el precio actual (bid)."""
    closed = []
    s = get_settings()
    for p in positions_of(db, account.id):
        if not (p.stop_loss or p.take_profit):
            continue
        try:
            q = quote(p.symbol, p.market)
        except Exception:
            continue
        bid = q["bid"]
        hit = "SL" if p.stop_loss and bid <= p.stop_loss else "TP" if p.take_profit and bid >= p.take_profit else None
        if hit:
            fill = bid * (1 - s.paper_slippage_bps / 10000)
            fee = p.quantity * fill * s.paper_fee_rate
            qty = p.quantity
            _close(db, account, p, qty, fill, fee)
            db.add(Order(account_id=account.id, provider=account.provider, environment=account.environment, origin=p.origin,
                         strategy_version_id=p.strategy_version_id, symbol=p.symbol, side="SELL", quantity=qty,
                         notional=qty * fill, status="filled", fill_price=fill, fee=fee, price_source=q.get("source", ""),
                         reason=f"Salida automática {hit}"))
            audit(db, "paper.exit_" + hit.lower(), account_id=account.id, symbol=p.symbol, price=fill)
            closed.append({"symbol": p.symbol, "hit": hit, "price": fill})
    return closed


def snapshot(db: Session, account: Account, quote: QuoteFn):
    eq, _, _ = equity_now(db, account, quote)
    db.add(EquitySnapshot(account_id=account.id, equity=eq, cash=account.cash))


def reset_paper(db: Session, account: Account, user_id: int):
    """Reinicio explícito y auditado: borra posiciones, conserva historial de órdenes/trades como archivo."""
    if account.environment != "paper":
        raise PaperError("Solo cuentas paper")
    for p in positions_of(db, account.id):
        db.delete(p)
    account.cash = account.initial_balance
    db.add(CashMovement(account_id=account.id, kind="reset", amount=account.initial_balance,
                        balance_after=account.cash, ref="reinicio explícito"))
    audit(db, "paper.reset", user_id, account.id, balance=account.initial_balance)


def summary(db: Session, account: Account, quote: QuoteFn) -> dict:
    trades = list(db.scalars(select(Trade).where(Trade.account_id == account.id).order_by(Trade.closed_at)))
    equity, pos_value, positions = equity_now(db, account, quote) if account.environment == "paper" else (0.0, 0.0, [])
    pnls = [t.pnl for t in trades]
    init = account.initial_balance
    snaps = list(db.scalars(select(EquitySnapshot).where(EquitySnapshot.account_id == account.id).order_by(EquitySnapshot.ts)))
    curve = [x.equity for x in snaps] or [init]
    if curve[-1] != equity and account.environment == "paper":
        curve.append(equity)
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _aware(d):
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

    month_trades = [t for t in trades if _aware(t.closed_at) >= month_start]
    week_ago = now - timedelta(days=7)
    wk = [t for t in trades if _aware(t.closed_at) >= week_ago]
    net = equity - init if account.environment == "paper" else 0.0
    return {
        "account_id": account.id, "provider": account.provider, "environment": account.environment, "currency": account.currency,
        "initial_balance": init, "cash": account.cash, "positions_value": pos_value, "equity": equity,
        "net_pnl": net, "net_pnl_pct": (net / init * 100) if init else None,
        "realized_pnl": sum(pnls), "unrealized_pnl": sum(p["unrealized"] for p in positions),
        "month_pnl": sum(t.pnl for t in month_trades), "month_pnl_pct": (sum(t.pnl for t in month_trades) / init * 100) if init else None,
        "trades": len(trades), "win_rate": metrics.win_rate(pnls), "profit_factor": metrics.profit_factor(pnls),
        "expectancy": metrics.expectancy(pnls), "max_drawdown_pct": metrics.max_drawdown(curve)["pct"],
        "trades_per_week": len(wk), "open_positions": positions, "kill_switch": account.kill_switch,
        "algo_allocation_fraction": get_settings().algo_allocation_fraction,
        "algo_target_notional": equity * get_settings().algo_allocation_fraction,
        "as_of": now.isoformat(),
    }
