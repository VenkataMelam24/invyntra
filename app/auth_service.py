# app/auth_service.py
import datetime
import re
import secrets
from typing import Optional, Tuple

import bcrypt
from sqlalchemy import select

from app.auth_models import AuthOTP, AuthUser, SessionLocal, ensure_auth_tables

# --- simple validators ---
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PWD_RE = re.compile(r"^(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{8,}$")  # >=8, 1 uppercase, 1 special


def normalize_phone(cc: str, num: str) -> Tuple[str, str, str]:
    cc = cc.strip()
    if not cc.startswith("+"):
        cc = "+" + cc
    digits = "".join(ch for ch in num if ch.isdigit())
    e164 = cc + digits
    return cc, digits, e164


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_user(
    first: str,
    last: str,
    business: str,
    email: str,
    cc: str,
    phone: str,
    pwd: str,
) -> Tuple[bool, str]:
    """Create a user after validating inputs.

    Returns (ok, message). Fails if phone/email already exist.
    """
    ensure_auth_tables()
    email_n = (email or "").strip().lower()
    if not EMAIL_RE.match(email_n):
        return False, "Invalid email format."
    if not PWD_RE.match(pwd or ""):
        return False, "Password must be at least 8 characters, include 1 uppercase and 1 special character."

    cc_n, digits, e164 = normalize_phone(cc, phone)
    if not digits:
        return False, "Phone number is required."

    session = SessionLocal()
    try:
        if session.execute(select(AuthUser).where(AuthUser.phone_e164 == e164)).scalar_one_or_none():
            return False, "Account already exists for this phone number."
        if session.execute(select(AuthUser).where(AuthUser.email == email_n)).scalar_one_or_none():
            return False, "Account already exists for this email."

        user = AuthUser(
            first_name=first.strip(),
            last_name=last.strip(),
            business_name=business.strip(),
            email=email_n,
            phone_cc=cc_n,
            phone_num=digits,
            phone_e164=e164,
            pwd_hash=hash_password(pwd),
            is_verified=True,
        )
        session.add(user)
        session.commit()
        return True, "Account created."
    finally:
        session.close()


def find_user_by_email_or_phone(identifier: str) -> Optional[AuthUser]:
    ensure_auth_tables()
    session = SessionLocal()
    try:
        ident = (identifier or "").strip()
        if "@" in ident:
            return session.execute(
                select(AuthUser).where(AuthUser.email == ident.lower())
            ).scalar_one_or_none()
        digits = "".join(ch for ch in ident if ch.isdigit() or ch == "+")
        if not digits.startswith("+"):
            users = session.execute(select(AuthUser)).scalars().all()
            for user in users:
                if user.phone_e164.endswith(digits):
                    return user
            return None
        return session.execute(
            select(AuthUser).where(AuthUser.phone_e164 == digits)
        ).scalar_one_or_none()
    finally:
        session.close()


def authenticate_credentials(identifier: str, password: str) -> Tuple[bool, Optional[AuthUser], str]:
    user = find_user_by_email_or_phone(identifier)
    if not user:
        return False, None, "Account not found."
    if not verify_password(password, user.pwd_hash):
        return False, None, "Invalid password."
    return True, user, "OK"


def generate_otp_for(user: AuthUser, purpose: str = "login") -> str:
    ensure_auth_tables()
    code = f"{secrets.randbelow(1000000):06d}"
    session = SessionLocal()
    try:
        otp = AuthOTP(
            email=user.email,
            phone_e164=user.phone_e164,
            code=code,
            purpose=purpose,
            expires_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=10),
        )
        session.add(otp)
        session.commit()
        print(f"[DEV] OTP for {user.email} / {user.phone_e164}: {code}")
        return code
    finally:
        session.close()


def verify_otp(identifier: str, code: str, purpose: str = "login") -> Tuple[bool, str]:
    ensure_auth_tables()
    user = find_user_by_email_or_phone(identifier)
    if not user:
        return False, "Account not found."
    session = SessionLocal()
    try:
        rows = session.execute(
            select(AuthOTP).where(
                AuthOTP.email == user.email,
                AuthOTP.phone_e164 == user.phone_e164,
                AuthOTP.purpose == purpose,
            )
        ).scalars().all()
        now = datetime.datetime.utcnow()
        for row in sorted(rows, key=lambda x: x.id, reverse=True):
            if now <= row.expires_at and row.code == code.strip():
                for existing in rows:
                    session.delete(existing)
                session.commit()
                return True, "Verified."
        return False, "Invalid or expired OTP."
    finally:
        session.close()


def reset_password(identifier: str, code: str, new_password: str) -> Tuple[bool, str]:
    """Verify a reset OTP for the identifier and set a new password."""
    if not PWD_RE.match(new_password or ""):
        return False, "Password must be at least 8 characters, include 1 uppercase and 1 special character."

    ok, msg = verify_otp(identifier, code, purpose="reset")
    if not ok:
        return False, msg

    user = find_user_by_email_or_phone(identifier)
    if not user:
        return False, "Account not found."

    session = SessionLocal()
    try:
        refreshed = session.get(AuthUser, user.id)
        if not refreshed:
            return False, "Account not found."
        refreshed.pwd_hash = hash_password(new_password)
        session.commit()
        return True, "Password updated."
    finally:
        session.close()


def update_business_name(identifier: str, new_name: str) -> Tuple[bool, str]:
    """Update the business name for a user located by email or phone."""
    ensure_auth_tables()
    user = find_user_by_email_or_phone(identifier)
    if not user:
        return False, "Account not found."
    session = SessionLocal()
    try:
        refreshed = session.get(AuthUser, user.id)
        if not refreshed:
            return False, "Account not found."
        refreshed.business_name = (new_name or "").strip() or refreshed.business_name
        session.commit()
        return True, "Business name updated."
    finally:
        session.close()
