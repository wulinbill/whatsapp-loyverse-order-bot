from loyverse_api import get_menu_items, create_order
from gpt_parser import parse_order

async def tool_parse_order(message: str) -> str:
    menu = await get_menu_items()
    items = [i["name"] for i in menu.get("items", [])]
    return parse_order(message, items)

async def tool_submit_order(order_json: str) -> dict:
    return await create_order(order_json)
