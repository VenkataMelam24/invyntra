# app/security.py
import secrets, string, datetime
from passlib.hash import bcrypt

def hash_password(pw: str) -> str:
    return bcrypt.hash(pw)

def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.verify(pw, hashed)
    except Exception:
        return False

def new_token() -> str:
    return secrets.token_urlsafe(32)

def new_otp() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))

def expires_in(minutes: int) -> datetime.datetime:
    return datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)
