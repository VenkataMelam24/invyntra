# app/dev_check.py
from sqlalchemy import select
from app.db import SessionLocal, engine
from app.models import Item, Txn

def main():
    s = SessionLocal()
    try:
        # upsert item "Rice"
        item = s.query(Item).filter_by(name="Rice").one_or_none()
        if not item:
            item = Item(name="Rice", unit="kg")
            s.add(item); s.commit(); s.refresh(item)

        # add a sample IN txn
        s.add(Txn(item_id=item.id, kind="IN", qty=10, note="test"))
        s.commit()

        items = s.execute(select(Item)).scalars().all()
        txns = s.execute(select(Txn)).scalars().all()
        print("DB:", engine.url.database)
        print("Items:", [(i.id, i.name, i.unit) for i in items])
        print("Txns :", [(t.id, t.item_id, t.kind, t.qty) for t in txns])
    finally:
        s.close()

if __name__ == "__main__":
    main()
