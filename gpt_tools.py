import asyncio
import json
from typing import Any, Dict, Union

from loyverse_api import get_menu_items, create_order
from gpt_parser import parse_order
from utils.logger import get_logger

logger = get_logger(__name__)


def _run_async(coro):
    """Run *coro* in a nested event-loop safe manner.

    The function is needed because the LangChain agent executes inside a
    regular (non-async) thread – therefore we have to spin up a short-lived
    event loop to call our async I/O helpers.
    """

    try:
        return asyncio.run(coro)
    except RuntimeError:
        # We are already inside an event loop (unlikely for the current
        # architecture, but safer). Create a new loop in a child thread.
        logger.debug("Detected existing event loop – running coroutine in a fresh loop")
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            asyncio.set_event_loop(None)


def tool_parse_order(message: str) -> str:
    """LangChain tool – convert free-text into order JSON using GPT-4o."""

    logger.info("Parsing order from message: %s", message[:80])

    menu: Dict[str, Any] = _run_async(get_menu_items())
    items = [i["name"] for i in menu.get("items", [])]
    return parse_order(message, items)


def tool_submit_order(order_json: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """LangChain tool – submit an order to Loyverse POS."""

    logger.info("Submitting order to Loyverse POS")

    if isinstance(order_json, str):
        try:
            order_data = json.loads(order_json)
        except json.JSONDecodeError as exc:
            logger.error("Order JSON decoding failed – input: %s", order_json)
            raise ValueError("Invalid order JSON") from exc
    else:
        order_data = order_json

    return _run_async(create_order(order_data))
