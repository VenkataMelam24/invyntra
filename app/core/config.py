import os
from dataclasses import dataclass


@dataclass
class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "Invyntra")
    ENV: str = os.getenv("INVYNTRA_ENV", "dev").lower()  # dev|stage|prod
    DEBUG: bool = os.getenv("DEBUG", "").lower() in {"1", "true", "yes"} or os.getenv("INVYNTRA_ENV", "dev").lower() != "prod"

    def __post_init__(self):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        db_name = f"invyntra_{self.ENV}.sqlite3"
        self.DATA_DIR = data_dir
        self.DB_PATH = os.path.join(data_dir, db_name)
        self.DATABASE_URL = f"sqlite:///{self.DB_PATH}"
        
        


# singleton settings
settings = Settings()

# Back-compat for modules importing DATABASE_URL directly
DATABASE_URL = settings.DATABASE_URL

# --- Email / SMTP (optional; if unset, we print emails to console) ---
SMTP_HOST = os.getenv("SMTP_HOST") or ""
SMTP_PORT = int(os.getenv("SMTP_PORT") or "587")
SMTP_USER = os.getenv("SMTP_USER") or ""
SMTP_PASS = os.getenv("SMTP_PASS") or ""
SMTP_TLS = (os.getenv("SMTP_TLS") or "1").lower() not in {"0", "false"}
SMTP_FROM = os.getenv("SMTP_FROM") or (settings.APP_NAME + " <no-reply@local>")

# For future deep links in emails
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8765")
