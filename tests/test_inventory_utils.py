from app.app.inventory_utils import parse_inventory_command


def test_parse_add_command_with_location():
    result = parse_inventory_command("add 5 kg of onions in pantry")
    assert result is not None
    assert result["action"] == "add"
    assert result["item"] == "onions"
    assert result["quantity"] == 5.0
    assert result["unit"] == "kg"
    assert result["location"] == "pantry"


def test_parse_remove_command_variants():
    result = parse_inventory_command("remove onions 2 kg from fridge")
    assert result is not None
    assert result["action"] == "remove"
    assert result["quantity"] == 2.0
    assert result["unit"] == "kg"
    assert result["location"] == "fridge"


def test_parse_invalid_command_returns_none():
    assert parse_inventory_command("hello world") is None
