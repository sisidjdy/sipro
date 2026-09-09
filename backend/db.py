"""MongoDB client + core config (loaded from .env).

Single shared Motor client. org scope is multi-tenant-ready (org_id on every
collection); SIPRO runs internal-first with a single default org.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Default tenant (internal-first). Every document carries org_id for future SaaS.
ORG_ID = os.environ.get("DEFAULT_ORG_ID", "org-sipro")
ORG_NAME = os.environ.get("DEFAULT_ORG_NAME", "Harmony Land 5")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = "none" if COOKIE_SECURE else "lax"
BOOKING_HOLD_DAYS = int(os.environ.get("BOOKING_HOLD_DAYS", "7"))
