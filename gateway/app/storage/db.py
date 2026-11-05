from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid4().hex


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    fail_mode: Mapped[str] = mapped_column(String(10), default="closed")  # open | closed
    loop_max_repeats: Mapped[int] = mapped_column(Integer, default=5)
    loop_window_seconds: Mapped[int] = mapped_column(Integer, default=60)
    require_identity: Mapped[bool] = mapped_column(Boolean, default=False)
    slack_webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(16))
    role: Mapped[str] = mapped_column(String(10), default="proxy")  # proxy | admin
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Policy(Base):
    """A budget: `limit_micro` per `window` for each id of `scope` (or one id)."""

    __tablename__ = "policies"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str] = mapped_column(String(10))  # tenant | agent | session | customer
    scope_id: Mapped[str | None] = mapped_column(String(128), nullable=True)  # None = each id
    window: Mapped[str] = mapped_column(String(10))  # total | minute | hour | day | month
    limit_micro: Mapped[int] = mapped_column(BigInteger)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class KillSwitch(Base):
    __tablename__ = "kill_switches"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(10))  # agent | session | customer
    scope_id: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    tenant_id: Mapped[str] = mapped_column(String(32))
    agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_micro: Mapped[int] = mapped_column(BigInteger, default=0)
    decision: Mapped[str] = mapped_column(String(32))  # allowed | budget_exceeded | loop_detected | ...
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    overhead_ms: Mapped[float] = mapped_column(default=0.0)
    stream: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_usage_tenant_ts", "tenant_id", "ts"),
        Index("ix_usage_tenant_session", "tenant_id", "session_id"),
        Index("ix_usage_tenant_agent", "tenant_id", "agent_id"),
    )


class AlertLog(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(32), index=True)
    policy_id: Mapped[str] = mapped_column(String(32))
    scope_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    threshold: Mapped[int] = mapped_column(Integer)  # 50 | 80 | 100
    spent_micro: Mapped[int] = mapped_column(BigInteger)
    limit_micro: Mapped[int] = mapped_column(BigInteger)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
