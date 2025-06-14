"""Loyverse OAuth2 自动刷新 Token"""
import os, httpx, time
from typing import Optional
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_fixed
from utils.logger import get_logger

load_dotenv()

logger = get_logger(__name__)

TOKEN_URL = "https://api.loyverse.com/oauth/token"
CLIENT_ID = os.getenv("LOYVERSE_CLIENT_ID")
CLIENT_SECRET = os.getenv("LOYVERSE_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("LOYVERSE_REFRESH_TOKEN")

if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
    missing = [k for k, v in {
        "LOYVERSE_CLIENT_ID": CLIENT_ID,
        "LOYVERSE_CLIENT_SECRET": CLIENT_SECRET,
        "LOYVERSE_REFRESH_TOKEN": REFRESH_TOKEN,
    }.items() if not v]
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

_access_token: Optional[str] = None
_expires_at = 0.0

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
async def _refresh():
    """Refresh the OAuth2 access token using the saved refresh token."""
    global _access_token, _expires_at, REFRESH_TOKEN
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    async with httpx.AsyncClient() as client:
        logger.debug("Refreshing Loyverse access token")
        r = await client.post(TOKEN_URL, data=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        _access_token = data["access_token"]
        REFRESH_TOKEN = data.get("refresh_token", REFRESH_TOKEN)
        _expires_at = time.time() + data["expires_in"] - 60

    logger.info("Loyverse access token refreshed – expires in %s seconds", data["expires_in"])

async def get_access_token() -> str:
    """Return a valid (refreshed if necessary) access token."""
    if _access_token is None or time.time() >= _expires_at:
        await _refresh()
    return _access_token
