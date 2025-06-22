import openai, os, json, pathlib, logging
from order_processor import convert
from tools import place_loyverse_order

openai.api_key = os.getenv("OPENAI_API_KEY")
logger = logging.getLogger(__name__)
SYSTEM = (pathlib.Path(__file__).parent / "prompts" / "system_prompt.txt").read_text()

def chat(messages):
    return openai.ChatCompletion.create(model=os.getenv("OPENAI_MODEL","gpt-4o-mini"),
                                        messages=messages,
                                        temperature=0.4).choices[0].message.content

def handle_message(from_id: str, text: str, history: list):
    history.append({"role":"user","content":text})
    messages=[{"role":"system","content":SYSTEM}]+history
    reply=chat(messages)
    history.append({"role":"assistant","content":reply})

    if "##JSON##" in reply:
        try:
            data=json.loads(reply.split("##JSON##",1)[1].strip())
            items=convert(data.get("sentences",[]))
            if items:
                receipt=place_loyverse_order(items)
                total=sum(i["price"]*i["quantity"] for i in items)/100
                reply=f"Perfecto. Tu total es ${total:.2f}. Recibo #{receipt}. ¡Gracias!"
        except Exception as e:
            logger.error("Post-processing failed: %s", e, exc_info=True)
    return reply
