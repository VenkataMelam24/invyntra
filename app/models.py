# app/models.py
from sqlalchemy import Column, Integer, String, DateTime, func, Index, ForeignKey
from sqlalchemy.orm import relationship
from .db import Base  # note the dot: relative import

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)   # e.g., "Rice"
    unit = Column(String, nullable=False, default="kg")  # "kg", "pcs", etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Txn(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    kind = Column(String, nullable=False)   # "IN" or "OUT"
    qty = Column(Integer, nullable=False)
    note = Column(String, nullable=True)
    ts = Column(DateTime(timezone=True), server_default=func.now())

    item = relationship("Item")

# Helpful indexes for dashboard queries
Index("ix_txn_ts", Txn.ts)
Index("ix_txn_item_ts", Txn.item_id, Txn.ts)
