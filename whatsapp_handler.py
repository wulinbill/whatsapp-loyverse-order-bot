from fastapi import Request
from twilio.twiml.messaging_response import MessagingResponse
from langchain_agent import get_agent
import asyncio

# 单实例 Agent
_AGENT = get_agent()

async def handle_whatsapp_message(request: Request) -> str:
    form = await request.form()
    user_msg = form.get("Body")

    # 多轮对话
    reply = await asyncio.to_thread(_AGENT.run, user_msg)

    response = MessagingResponse()
    response.message(reply)
    return str(response)
