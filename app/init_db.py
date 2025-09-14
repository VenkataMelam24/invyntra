from .db import engine, Base
from . import models   # registers Item/Txn tables

Base.metadata.create_all(bind=engine)
print(f"Tables created at -> {engine.url.database}")
