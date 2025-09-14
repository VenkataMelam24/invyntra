# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict  # <-- changed import
from dotenv import load_dotenv
import os, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def _branch_name() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or "dev"
    except Exception:
        return "dev"

def _env_file_path() -> Path:
    name = os.getenv("APP_ENV")
    if not name:
        br = _branch_name()
        if br == "main":
            name = "prod"
        elif br in {"dev", "stage"}:
            name = br
        else:
            name = "dev"
    return ROOT / f".env.{name}"

ENV_FILE = _env_file_path()
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
    print(f"[config] loaded {ENV_FILE.name}")
else:
    print(f"[config] {ENV_FILE.name} not found (using defaults/OS env)")

class Settings(BaseSettings):
    ENV: str = "dev"
    APP_NAME: str = "Invyntra"
    DEBUG: int = 0

    # pydantic v2 style config
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",          # optional extra overrides
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()

# --- DB paths/URL derived from the active env ---
from pathlib import Path

DATA_DIR = (ROOT / "data")
DATA_DIR.mkdir(exist_ok=True)

DATABASE_FILE = DATA_DIR / f"invyntra_{settings.ENV}.sqlite3"   # dev/stage/prod-specific file
DATABASE_URL = f"sqlite:///{DATABASE_FILE}"
print(f"[config] DB → {DATABASE_FILE.name}")
