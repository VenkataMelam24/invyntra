import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.auth_models as auth_models
import app.auth_service as auth_service


@pytest.fixture()
def auth_session():
    old_engine = auth_models.engine
    old_session_local = auth_models.SessionLocal
    old_service_session = auth_service.SessionLocal

    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)

    auth_models.engine = engine
    auth_models.SessionLocal = Session
    auth_service.SessionLocal = Session
    auth_models.BaseAuth.metadata.create_all(bind=engine)

    try:
        yield Session
    finally:
        auth_models.BaseAuth.metadata.drop_all(bind=engine)
        auth_models.engine = old_engine
        auth_models.SessionLocal = old_session_local
        auth_service.SessionLocal = old_service_session


def test_create_user_success(auth_session):
    ok, msg = auth_service.create_user(
        "Ada",
        "Lovelace",
        "Analytical Diner",
        "ada@example.com",
        "+1",
        "5551234567",
        "Strong@123",
    )
    assert ok
    assert "Account created" in msg
    with auth_session() as session:
        users = session.execute(select(auth_models.AuthUser)).scalars().all()
        assert len(users) == 1
        assert users[0].email == "ada@example.com"


def test_create_user_duplicate_email(auth_session):
    auth_service.create_user(
        "Ada",
        "Lovelace",
        "Analytical Diner",
        "ada@example.com",
        "+1",
        "5551234567",
        "Strong@123",
    )
    ok, msg = auth_service.create_user(
        "Charles",
        "Babbage",
        "Analytical Diner",
        "ada@example.com",
        "+1",
        "5557654321",
        "Another@123",
    )
    assert not ok
    assert "email" in msg.lower()


def test_create_user_rejects_weak_password(auth_session):
    ok, msg = auth_service.create_user(
        "Grace",
        "Hopper",
        "Debug Bistro",
        "grace@example.com",
        "+1",
        "5551112222",
        "weakpass",
    )
    assert not ok
    assert "password" in msg.lower()
