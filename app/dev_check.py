# app/dev_check.py
from app.services.inventory_service import InventoryService, InventoryError


def main():
    service = InventoryService("dev@example.com")
    try:
        record = service.record_command(
            {
                "action": "add",
                "item": "Rice",
                "quantity": 10,
                "unit": "kg",
                "location": "dry store",
                "note": "dev sample",
            },
            actor="dev",
            source="dev_check",
        )
        print("Recorded:", record)
    except InventoryError as exc:
        print("Inventory error:", exc)
    rows = service.list_transactions()
    print("Transactions:")
    for row in rows:
        print(" -", row)
    print("Aggregate:")
    for agg in service.aggregate_inventory():
        print(" -", agg)


if __name__ == "__main__":
    main()
