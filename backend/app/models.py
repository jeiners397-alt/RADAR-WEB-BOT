"""Modelo de datos. Toda tabla sensible a cuenta lleva account_id; la cuenta fija provider+environment."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="admin")
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SessionRow(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 del token
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProviderConnection(Base):
    """Credenciales cifradas (Fernet). El secreto NUNCA se devuelve por API."""
    __tablename__ = "provider_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(16))
    masked: Mapped[str] = mapped_column(String(32))
    secret_blob: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # servidor, login, plataforma (no secretos)
    trading_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(16))        # binance|exness|mt5
    environment: Mapped[str] = mapped_column(String(16))     # public|paper|demo|live
    name: Mapped[str] = mapped_column(String(80))
    currency: Mapped[str] = mapped_column(String(8), default="USDT")
    status: Mapped[str] = mapped_column(String(24), default="connected")
    connection_id: Mapped[int | None] = mapped_column(ForeignKey("provider_connections.id"), nullable=True)
    initial_balance: Mapped[float] = mapped_column(Float, default=0.0)
    cash: Mapped[float] = mapped_column(Float, default=0.0)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CashMovement(Base):
    __tablename__ = "cash_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))  # initial|fill_buy|fill_sell|reset
    amount: Mapped[float] = mapped_column(Float)
    balance_after: Mapped[float] = mapped_column(Float)
    ref: Mapped[str] = mapped_column(String(64), default="")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StrategyDef(Base):
    __tablename__ = "strategy_definitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(80))
    template: Mapped[str] = mapped_column(String(40))
    notes: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    active_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (UniqueConstraint("user_id", "code"),)


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategy_definitions.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StrategyAccountState(Base):
    """Habilitación por cuenta (paper). Por defecto deshabilitada."""
    __tablename__ = "strategy_account_state"
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategy_definitions.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("strategy_id", "account_id"),)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    provider: Mapped[str] = mapped_column(String(16))
    environment: Mapped[str] = mapped_column(String(16))
    origin: Mapped[str] = mapped_column(String(12))  # MANUAL | ALGORITHM
    strategy_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbol: Mapped[str] = mapped_column(String(24))
    market: Mapped[str] = mapped_column(String(12), default="spot")
    side: Mapped[str] = mapped_column(String(4))
    type: Mapped[str] = mapped_column(String(8), default="market")
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    notional: Mapped[float] = mapped_column(Float, default=0.0)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(12))  # filled|rejected
    reject_reason: Mapped[str] = mapped_column(String(200), default="")
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    price_source: Mapped[str] = mapped_column(String(80), default="")
    reason: Mapped[str] = mapped_column(String(200), default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sizing: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("account_id", "idempotency_key"),)


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(24))
    market: Mapped[str] = mapped_column(String(12), default="spot")
    quantity: Mapped[float] = mapped_column(Float)
    avg_price: Mapped[float] = mapped_column(Float)
    origin: Mapped[str] = mapped_column(String(12))
    strategy_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    entry_fee: Mapped[float] = mapped_column(Float, default=0.0)
    __table_args__ = (UniqueConstraint("account_id", "symbol", "market"),)


class Trade(Base):
    """Operación cerrada: base de todos los KPIs."""
    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(24))
    origin: Mapped[str] = mapped_column(String(12))
    strategy_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    fees: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float] = mapped_column(Float)  # neto de comisiones
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TradeSample(Base):
    __tablename__ = "trade_samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id"), index=True)
    seconds_since_entry: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    equity: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)


class RiskRule(Base):
    __tablename__ = "risk_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), unique=True)
    max_open_positions: Mapped[int] = mapped_column(Integer, default=5)
    max_total_exposure_pct: Mapped[float] = mapped_column(Float, default=60.0)
    max_daily_loss_pct: Mapped[float] = mapped_column(Float, default=10.0)
    max_order_notional: Mapped[float | None] = mapped_column(Float, nullable=True)


class ResearchJob(Base):
    __tablename__ = "research_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(16), default="binance")
    market: Mapped[str] = mapped_column(String(12), default="spot")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(12), default="running")  # running|paused|cancelled|done
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobTask(Base):
    __tablename__ = "job_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("research_jobs.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(24))
    timeframe: Mapped[str] = mapped_column(String(6))
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|running|completed|skipped|failed
    worker_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(300), default="")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("job_id", "symbol", "timeframe"), Index("ix_task_claim", "job_id", "status"))


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    worker_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # research|market
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    info: Mapped[dict] = mapped_column(JSON, default=dict)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    strategy_version_id: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12), default="queued")  # queued|running|done|failed
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str] = mapped_column(String(300), default="")
    dataset_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ServerMetric(Base):
    __tablename__ = "server_metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    cpu: Mapped[float] = mapped_column(Float)
    ram: Mapped[float] = mapped_column(Float)
    disk: Mapped[float] = mapped_column(Float)
    api_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(48))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    level: Mapped[str] = mapped_column(String(8), default="info")
    text: Mapped[str] = mapped_column(String(300))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
