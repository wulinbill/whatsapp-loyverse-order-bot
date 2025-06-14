import os
from dotenv import load_dotenv
from openai import OpenAI
import json
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)

load_dotenv()

openai_key = os.getenv("OPENAI_API_KEY")
if not openai_key:
    raise RuntimeError("Environment variable OPENAI_API_KEY is required but missing.")

_client = OpenAI(api_key=openai_key)

prompt_path = Path("prompt_templates") / "order_prompt.txt"
SYSTEM_PROMPT = prompt_path.read_text(encoding="utf-8")

def parse_order(message: str, menu_items: list[str]) -> str:
    """Invoke GPT model to convert a natural-language order into JSON.

    The function is synchronous because it is executed inside a worker
    thread (see *whatsapp_handler.py*).  Any exception is propagated
    upwards so that the caller can decide how to handle it.
    """
    try:
        logger.debug("Sending order parsing prompt to OpenAI")
        resp = _client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"客户内容: {message}\n菜单列表: {json.dumps(menu_items, ensure_ascii=False)}",
                },
            ],
        )
        content: str = resp.choices[0].message.content.strip()
        logger.debug("Raw GPT output: %s", content)
        return content
    except Exception:
        logger.exception("Failed to parse order via OpenAI")
        raise
