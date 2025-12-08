import os
from dotenv import load_dotenv

# Load variables from a local .env file if present (safe for local dev)
# In production, rely on real environment variables instead.
load_dotenv(override=True)

# === Telegram Bot ===
TOKEN = os.getenv("BOT_TOKEN")
MANAGER_URL = os.getenv("MANAGER_URL", "https://t.me/your_manager")
# Use 0 if MANAGER_GROUP is not set (no notifications). Negative for channels/supergroups.
MANAGER_GROUP = int(os.getenv("MANAGER_GROUP", "0"))

# === Crypto Bot (CryptoPay / aiosend) ===
ASSET = os.getenv("CRYPTO_ASSET", "USDT")
CRYPTOTOKEN = os.getenv("CRYPTO_TOKEN")
ASSET = os.getenv("CRYPTO_ASSET", "USDT")
CRYPTOTOKEN = os.getenv("CRYPTO_TOKEN")
CRYPTO_ENABLED = os.getenv("CRYPTO_ENABLED", "1") == "1"

# === YooKassa ===
ACCOUNT_ID = os.getenv("YOOKASSA_ACCOUNT_ID")
SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

# === Pricing ===
# Keep amounts as strings if your payment provider wants strings (e.g., YooKassa).
AMOUNT_bot = int(os.getenv("AMOUNT_BOT", "1"))
PRICE_bot = os.getenv("PRICE_BOT", "190.0")
AMOUNT_premium = int(os.getenv("AMOUNT_PREMIUM", "2"))
PRICE_premium = os.getenv("PRICE_PREMIUM", "380.0")

# === Google Service Account (for Google Docs API) ===
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")

# === Google OAuth Account ===
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI")
OAUTH_HOST = os.getenv("OAUTH_HOST", "0.0.0.0")
OAUTH_PORT = int(os.getenv("OAUTH_PORT", "8080"))
OAUTH_STATE_SECRET = os.getenv("OAUTH_STATE_SECRET", "super_secret_random_string")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")

# === Redis (for caching) ===
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

DB_PATH = os.getenv("DB_PATH", "db.db")

# === Strict Mode (optional) ===
# Set to "1" to fail fast when critical vars are missing.
STRICT_ENV = os.getenv("STRICT_ENV", "0") == "1"

def _require(name: str, value: str | None):
    if STRICT_ENV and not value:
        raise RuntimeError(f"Required env var {name} is not set. Check your .env or environment.")

# Enforce critical variables only if STRICT_ENV enabled
for _n in ["BOT_TOKEN", "CRYPTO_TOKEN", "YOOKASSA_ACCOUNT_ID", "YOOKASSA_SECRET_KEY"]:
    _require(_n, os.getenv(_n))
