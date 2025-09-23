# app/models.py
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    func,
    Index,
    ForeignKey,
    Boolean,
    Text,
    Float,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from .db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    business = Column(String, nullable=False)             # Business Name
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    country_code = Column(String, nullable=False, default="+")
    phone = Column(String, unique=True, nullable=False)
    password_h = Column(String, nullable=False)           # hashed password
    is_verified = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EmailToken(Base):
    __tablename__ = "email_tokens"
    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False)
    purpose = Column(String, nullable=False)              # "verify" | "reset"
    token = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    payload = Column(Text, nullable=True)                 # optional JSON
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    owner_key = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    normalized_name = Column(String, nullable=False)
    unit = Column(String, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("owner_key", "normalized_name", name="uq_items_owner_name"),
    )


class Txn(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    owner_key = Column(String, nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    kind = Column(String, nullable=False)   # "IN" or "OUT"
    qty = Column(Float, nullable=False)
    unit = Column(String, nullable=False, default="")
    note = Column(String, nullable=True)
    location = Column(String, nullable=True)
    location_normalized = Column(String, nullable=False, default="")
    entered_by = Column(String, nullable=True)
    source = Column(String, nullable=True)
    raw_payload = Column(Text, nullable=True)
    ts = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    item = relationship("Item")


Index("ix_txn_owner_item_ts", Txn.owner_key, Txn.item_id, Txn.ts)
Index("ix_txn_owner_location", Txn.owner_key, Txn.location_normalized)


class StockSnapshot(Base):
    __tablename__ = "stock_snapshots"
    id = Column(Integer, primary_key=True)
    owner_key = Column(String, nullable=False, index=True)
    label = Column(String, nullable=True)
    actor = Column(String, nullable=True)
    data = Column(Text, nullable=False)  # JSON payload of aggregated stock
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    owner_key = Column(String, nullable=False, index=True)
    actor = Column(String, nullable=True)
    action = Column(String, nullable=False)
    entity = Column(String, nullable=True)
    reference_id = Column(Integer, nullable=True)
    payload = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Helpful indexes for dashboard queries
Index("ix_audit_owner_created", AuditLog.owner_key, AuditLog.created_at)
