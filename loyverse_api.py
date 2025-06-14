import os, httpx, json
from loyverse_auth import get_access_token

LOYVERSE_API_URL = "https://api.loyverse.com/v1.0"
STORE_ID = os.getenv("LOYVERSE_STORE_ID")

async def _headers():
    token = await get_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

async def get_menu_items(cache_path: str = "menu_data.json") -> dict:
    try:
        return json.load(open(cache_path, "r", encoding="utf-8"))
    except FileNotFoundError:
        pass
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{LOYVERSE_API_URL}/items", headers=await _headers())
        r.raise_for_status()
        data = r.json()
        json.dump(data, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return data

async def create_order(order_data: dict) -> dict:
    order_data.setdefault("store_id", STORE_ID)
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{LOYVERSE_API_URL}/sales", headers=await _headers(), json=order_data)
        r.raise_for_status()
        return r.json()
