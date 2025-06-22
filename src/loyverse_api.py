import os, httpx, logging
from loyverse_auth import get_access_token
logger = logging.getLogger(__name__)
BASE = "https://api.loyverse.com/v1.0"

def place_order(payload: dict):
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type":"application/json"}
    store_id = os.getenv("LOYVERSE_STORE_ID")
    r = httpx.post(f"{BASE}/stores/{store_id}/orders", json=payload, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    logger.info("Order placed: %s", data.get("receipt_number"))
    return data
