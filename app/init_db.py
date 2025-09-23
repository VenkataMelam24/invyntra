from .db import engine, Base
from .db_migrations import run_migrations
from . import models   # registers Item/Txn tables

Base.metadata.create_all(bind=engine)
run_migrations(engine)
print(f"Tables created at -> {engine.url.database}")

