import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import AuditLog, Item, StockSnapshot, Txn
from app.services.inventory_service import InventoryError, InventoryService


@pytest.fixture()
def inventory_service():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(bind=engine)
    service = InventoryService("owner@example.com", session_factory=Session)
    return service, Session


def test_record_command_creates_transaction_and_audit(inventory_service):
    service, Session = inventory_service
    record = service.record_command(
        {
            "action": "add",
            "item": "Rice",
            "quantity": 10,
            "unit": "kg",
            "location": "dry store",
            "note": "restock",
        },
        actor="tester",
        source="voice",
    )
    assert record.action == "add"
    with Session() as session:
        txns = session.execute(select(Txn)).scalars().all()
        assert len(txns) == 1
        audits = session.execute(select(AuditLog)).scalars().all()
        assert len(audits) == 1
        assert txns[0].owner_key == "owner@example.com"


def test_remove_more_than_available_raises(inventory_service):
    service, _ = inventory_service
    service.record_command(
        {
            "action": "add",
            "item": "Oil",
            "quantity": 3,
            "unit": "l",
            "location": "kitchen",
        },
        actor="tester",
    )
    with pytest.raises(InventoryError):
        service.record_command(
            {
                "action": "remove",
                "item": "Oil",
                "quantity": 5,
                "unit": "l",
                "location": "kitchen",
            },
            actor="tester",
        )


def test_create_snapshot_persists_data(inventory_service):
    service, Session = inventory_service
    service.record_command(
        {
            "action": "add",
            "item": "Tomatoes",
            "quantity": 8,
            "unit": "kg",
            "location": "cooler",
        },
        actor="tester",
    )
    snapshot = service.create_snapshot(actor="tester", label="closing")
    assert snapshot["data"]
    with Session() as session:
        snaps = session.execute(select(StockSnapshot)).scalars().all()
        assert len(snaps) == 1


def test_delete_transactions_clears_rows(inventory_service):
    service, Session = inventory_service
    rec1 = service.record_command(
        {
            "action": "add",
            "item": "Sugar",
            "quantity": 4,
            "unit": "kg",
        },
        actor="tester",
    )
    rec2 = service.record_command(
        {
            "action": "add",
            "item": "Sugar",
            "quantity": 2,
            "unit": "kg",
        },
        actor="tester",
    )
    deleted = service.delete_transactions([rec1.id, rec2.id], actor="tester")
    assert deleted == 2
    with Session() as session:
        txns = session.execute(select(Txn)).scalars().all()
        assert not txns
        audits = session.execute(select(AuditLog)).scalars().all()
        assert len(audits) == 4  # two adds + two deletes


def test_aggregate_inventory_returns_normalised(inventory_service):
    service, _ = inventory_service
    service.record_command(
        {
            "action": "add",
            "item": "Flour",
            "quantity": 5,
            "unit": "kg",
            "location": "store",
        },
        actor="tester",
    )
    service.record_command(
        {
            "action": "remove",
            "item": "Flour",
            "quantity": 2,
            "unit": "kg",
            "location": "store",
        },
        actor="tester",
    )
    totals = service.aggregate_inventory()
    assert totals == [{"item": "flour", "unit": "kg", "location": "store", "net_quantity": 3.0}]
