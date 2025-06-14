import os, httpx, json
from loyverse_auth import get_access_token
from utils.logger import get_logger

logger = get_logger(__name__)

LOYVERSE_API_URL = "https://api.loyverse.com/v1.0"
STORE_ID = os.getenv("LOYVERSE_STORE_ID")

if not STORE_ID:
    raise RuntimeError("Environment variable LOYVERSE_STORE_ID is required but missing.")

async def _headers():
    token = await get_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

async def get_menu_items(cache_path: str = "menu_data.json") -> dict:
    try:
        cached = json.load(open(cache_path, "r", encoding="utf-8"))
        logger.debug("Loaded menu from cache – %s items", len(cached.get("items", [])))
        return cached
    except FileNotFoundError:
        logger.info("Menu cache not found – pulling from Loyverse API")
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{LOYVERSE_API_URL}/items",
            headers=await _headers(),
            params={"limit": 250},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        json.dump(data, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        logger.info("Menu cached – %s items", len(data.get("items", [])))
        return data

async def create_order(order_data: dict) -> dict:
    order_data.setdefault("store_id", STORE_ID)
    logger.debug("Creating Loyverse order: %s", order_data)
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{LOYVERSE_API_URL}/sales",
            headers=await _headers(),
            json=order_data,
            timeout=15,
        )
        r.raise_for_status()
        resp_json = r.json()
        logger.info("Order created successfully – id: %s", resp_json.get("sale_id"))
        return resp_json
