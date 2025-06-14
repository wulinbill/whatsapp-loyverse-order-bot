"""Loyverse OAuth2 自动刷新 Token"""
import os, httpx, time
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_fixed

load_dotenv()

TOKEN_URL = "https://api.loyverse.com/oauth/token"
CLIENT_ID = os.getenv("LOYVERSE_CLIENT_ID")
CLIENT_SECRET = os.getenv("LOYVERSE_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("LOYVERSE_REFRESH_TOKEN")

_access_token = None
_expires_at = 0.0

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def _refresh():
    global _access_token, _expires_at, REFRESH_TOKEN
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(TOKEN_URL, data=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        _access_token = data["access_token"]
        REFRESH_TOKEN = data.get("refresh_token", REFRESH_TOKEN)
        _expires_at = time.time() + data["expires_in"] - 60

async def get_access_token() -> str:
    if _access_token is None or time.time() >= _expires_at:
        await _refresh()
    return _access_token
