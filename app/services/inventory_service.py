"""Database-backed inventory operations for UI and voice commands."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional

from sqlalchemy import case, delete, select
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.app.inventory_utils import _clean_item, _normalize_unit
from app.db_migrations import run_migrations
from app.models import AuditLog, Item, StockSnapshot, Txn


class InventoryError(Exception):
    """Raised when an inventory command cannot be processed."""


@dataclass
class InventoryRecord:
    id: int
    timestamp: str
    action: str
    item: str
    quantity: float
    unit: str
    location: str
    note: str
    by: str
    source: str


def _clean_owner(owner_key: str | None) -> str:
    key = (owner_key or "").strip()
    return key.lower()


def _normalize_location(location: str | None) -> str:
    return (location or "").strip().lower()


_MIGRATIONS_APPLIED = False

def _ensure_migrations():
    global _MIGRATIONS_APPLIED
    if not _MIGRATIONS_APPLIED:
        run_migrations(engine)
        _MIGRATIONS_APPLIED = True

class InventoryService:
    """High-level inventory operations for a single account."""

    def __init__(self, owner_key: str, session_factory: Callable[[], Session] = SessionLocal):
        _ensure_migrations()
        key = _clean_owner(owner_key)
        if not key:
            raise ValueError("owner_key is required for InventoryService")
        self._owner_key = key
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Helpers
    def _session(self) -> Session:
        return self._session_factory()

    def _ensure_item(self, session: Session, item_raw: str, unit_norm: str) -> Item:
        normalized = _clean_item(item_raw).lower()
        if not normalized:
            raise InventoryError("Item name is required.")
        stmt = (
            select(Item)
            .where(Item.owner_key == self._owner_key, Item.normalized_name == normalized)
            .limit(1)
        )
        item = session.execute(stmt).scalar_one_or_none()
        if item:
            if unit_norm and not item.unit:
                item.unit = unit_norm
            return item
        item = Item(
            owner_key=self._owner_key,
            name=item_raw.strip() or normalized,
            normalized_name=normalized,
            unit=unit_norm,
        )
        session.add(item)
        session.flush()
        return item

    def _available_quantity(self, session: Session, item: Item, location_norm: str) -> float:
        stmt = (
            select(
                case((Txn.kind == "IN", Txn.qty), else_=-Txn.qty)
            )
            .where(Txn.owner_key == self._owner_key, Txn.item_id == item.id)
        )
        if location_norm:
            stmt = stmt.where(Txn.location_normalized == location_norm)
        else:
            stmt = stmt.where(Txn.location_normalized == "")
        rows = session.execute(stmt).scalars().all()
        return float(sum(rows)) if rows else 0.0

    def _record_to_dict(self, txn: Txn, item: Item) -> InventoryRecord:
        return InventoryRecord(
            id=txn.id,
            timestamp=(txn.ts.isoformat() if txn.ts else ""),
            action="add" if txn.kind == "IN" else "remove",
            item=item.name,
            quantity=float(txn.qty),
            unit=txn.unit or item.unit or "",
            location=txn.location or "",
            note=txn.note or "",
            by=txn.entered_by or "",
            source=txn.source or "",
        )

    def _audit(self, session: Session, *, actor: str, action: str, entity: str, reference_id: int | None, payload: dict):
        audit = AuditLog(
            owner_key=self._owner_key,
            actor=actor,
            action=action,
            entity=entity,
            reference_id=reference_id,
            payload=json.dumps(payload, ensure_ascii=False),
        )
        session.add(audit)

    # ------------------------------------------------------------------
    # Public API
    def record_command(
        self,
        command: Dict[str, object],
        *,
        actor: str,
        source: str = "manual",
    ) -> InventoryRecord:
        quantity_raw = command.get("quantity")
        try:
            quantity = float(quantity_raw) if quantity_raw not in (None, "") else math.nan
        except Exception as exc:
            raise InventoryError("Quantity must be numeric.") from exc

        action_raw = (command.get("action") or "").strip().lower()
        if action_raw not in {"add", "remove"}:
            raise InventoryError("Action must be 'add' or 'remove'.")

        if math.isnan(quantity) or quantity <= 0:
            raise InventoryError("Quantity must be greater than zero.")

        unit_norm = _normalize_unit(command.get("unit") or "")
        location = (command.get("location") or "").strip()
        location_norm = _normalize_location(location)
        note = (command.get("note") or "").strip()
        item_raw = (command.get("item") or "").strip()
        actor_name = (actor or "").strip()

        session = self._session()
        try:
            item = self._ensure_item(session, item_raw, unit_norm)
            if not unit_norm:
                unit_norm = item.unit or ""
            kind = "IN" if action_raw == "add" else "OUT"

            if kind == "OUT":
                available = self._available_quantity(session, item, location_norm)
                if quantity > available + 1e-9:
                    raise InventoryError(
                        f"Only {available:g} {unit_norm or item.unit} of {item.name} available in {location or 'default stock'}."
                    )

            txn = Txn(
                owner_key=self._owner_key,
                item_id=item.id,
                kind=kind,
                qty=quantity,
                unit=unit_norm or item.unit or "",
                note=note,
                location=location,
                location_normalized=location_norm,
                entered_by=actor_name,
                source=source,
                raw_payload=json.dumps(command, ensure_ascii=False),
            )
            session.add(txn)
            session.flush()
            session.refresh(txn)

            self._audit(
                session,
                actor=actor_name,
                action=f"inventory.{action_raw}",
                entity="txn",
                reference_id=txn.id,
                payload={
                    "item": item.name,
                    "quantity": quantity,
                    "unit": txn.unit,
                    "location": txn.location,
                    "source": source,
                },
            )
            session.commit()
            session.refresh(item)
            return self._record_to_dict(txn, item)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_transactions(self) -> List[InventoryRecord]:
        session = self._session()
        try:
            stmt = (
                select(Txn, Item)
                .join(Item, Item.id == Txn.item_id)
                .where(Txn.owner_key == self._owner_key)
                .order_by(Txn.ts.asc())
            )
            records: List[InventoryRecord] = []
            for txn, item in session.execute(stmt).all():
                records.append(self._record_to_dict(txn, item))
            return records
        finally:
            session.close()

    def delete_transactions(self, txn_ids: Iterable[int], *, actor: str) -> int:
        ids = [int(i) for i in txn_ids if i is not None]
        if not ids:
            return 0
        session = self._session()
        try:
            stmt = (
                select(Txn, Item)
                .join(Item, Item.id == Txn.item_id)
                .where(Txn.owner_key == self._owner_key, Txn.id.in_(ids))
            )
            rows = session.execute(stmt).all()
            deleted = session.execute(
                delete(Txn).where(Txn.owner_key == self._owner_key, Txn.id.in_(ids))
            ).rowcount or 0
            if deleted:
                for txn, item in rows:
                    self._audit(
                        session,
                        actor=actor,
                        action="inventory.delete",
                        entity="txn",
                        reference_id=txn.id,
                        payload={
                            "item": item.name,
                            "quantity": txn.qty,
                            "unit": txn.unit,
                            "location": txn.location,
                        },
                    )
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def clear_transactions(self, *, actor: str) -> int:
        session = self._session()
        try:
            stmt = (
                select(Txn.id)
                .where(Txn.owner_key == self._owner_key)
            )
            ids = [row[0] for row in session.execute(stmt).all()]
            if not ids:
                return 0
            count = self.delete_transactions(ids, actor=actor)
            return count
        finally:
            session.close()

    def aggregate_inventory(self) -> List[dict]:
        rows = self.list_transactions()
        totals: Dict[tuple[str, str, str], float] = {}
        for rec in rows:
            key = (_clean_item(rec.item).lower(), _normalize_unit(rec.unit), rec.location.strip().lower())
            qty = rec.quantity if rec.action == "add" else -rec.quantity
            totals[key] = totals.get(key, 0.0) + qty
        result = []
        for (item_norm, unit_norm, loc_norm), net in totals.items():
            result.append(
                {
                    "item": item_norm,
                    "unit": unit_norm,
                    "location": loc_norm,
                    "net_quantity": net,
                }
            )
        result.sort(key=lambda r: (r["item"], r["location"], r["unit"]))
        return result

    def create_snapshot(self, *, actor: str, label: Optional[str] = None) -> dict:
        snapshot_rows = self.aggregate_inventory()
        session = self._session()
        try:
            snap = StockSnapshot(
                owner_key=self._owner_key,
                label=(label or "").strip() or None,
                actor=actor,
                data=json.dumps(snapshot_rows, ensure_ascii=False),
            )
            session.add(snap)
            session.flush()
            session.refresh(snap)
            self._audit(
                session,
                actor=actor,
                action="inventory.snapshot",
                entity="snapshot",
                reference_id=snap.id,
                payload={"label": snap.label, "count": len(snapshot_rows)},
            )
            session.commit()
            return {
                "id": snap.id,
                "label": snap.label or "",
                "actor": snap.actor or "",
                "created_at": snap.created_at.isoformat() if snap.created_at else "",
                "data": snapshot_rows,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_snapshots(self) -> List[dict]:
        session = self._session()
        try:
            stmt = (
                select(StockSnapshot)
                .where(StockSnapshot.owner_key == self._owner_key)
                .order_by(StockSnapshot.created_at.desc())
            )
            out = []
            for snap, in session.execute(stmt):
                try:
                    data = json.loads(snap.data)
                except Exception:
                    data = []
                out.append(
                    {
                        "id": snap.id,
                        "label": snap.label or "",
                        "actor": snap.actor or "",
                        "created_at": snap.created_at.isoformat() if snap.created_at else "",
                        "data": data,
                    }
                )
            return out
        finally:
            session.close()

    def delete_snapshot(self, snapshot_id: int, *, actor: str) -> bool:
        session = self._session()
        try:
            snap = (
                session.query(StockSnapshot)
                .filter(StockSnapshot.owner_key == self._owner_key, StockSnapshot.id == snapshot_id)
                .one_or_none()
            )
            if not snap:
                return False
            session.delete(snap)
            self._audit(
                session,
                actor=actor,
                action="inventory.snapshot.delete",
                entity="snapshot",
                reference_id=snapshot_id,
                payload={"label": snap.label or ""},
            )
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


