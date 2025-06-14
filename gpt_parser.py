import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
SYSTEM_PROMPT = open("prompt_templates/order_prompt.txt", "r", encoding="utf-8").read()

def parse_order(message: str, menu_items: list[str]) -> str:
    resp = _client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"客户内容: {message}\n菜单列表: {menu_items}"}
        ]
    )
    return resp.choices[0].message.content
