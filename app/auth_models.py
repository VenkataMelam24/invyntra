# app/auth_models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase
from app.db import engine
from sqlalchemy.orm import sessionmaker

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

class BaseAuth(DeclarativeBase):
    pass

class AuthUser(BaseAuth):
    __tablename__ = "auth_users"
    id = Column(Integer, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    business_name = Column(String, nullable=False)
    email = Column(String, nullable=False)   # unique below (case-insensitive handling in code)
    phone_cc = Column(String, nullable=False)  # country code like +1, +91
    phone_num = Column(String, nullable=False) # digits only
    phone_e164 = Column(String, nullable=False)  # normalized like +919876543210
    pwd_hash = Column(String, nullable=False)
    is_verified = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("phone_e164", name="uq_auth_phone"),
        UniqueConstraint("email", name="uq_auth_email"),
    )

class AuthOTP(BaseAuth):
    __tablename__ = "auth_otps"
    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False)       # send to email
    phone_e164 = Column(String, nullable=False)  # and phone
    code = Column(String, nullable=False)        # 6 digits
    purpose = Column(String, nullable=False)     # "login"
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

def ensure_auth_tables():
    BaseAuth.metadata.create_all(bind=engine)
