from fastapi import Request
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse
from langchain_agent import get_agent
import asyncio
from utils.logger import get_logger

# 单实例 Agent
_AGENT = get_agent()

logger = get_logger(__name__)

async def handle_whatsapp_message(request: Request) -> Response:
    """Parse an incoming Twilio WhatsApp request and generate a reply.

    The function is intentionally *resilient*: any unexpected exception is
    swallowed and converted into a generic apology message so that the
    customer experience is not negatively impacted.
    """

    try:
        form = await request.form()
        user_msg = (form.get("Body") or "").strip()

        if not user_msg:
            logger.warning("Received WhatsApp message without body – ignoring")
            user_msg = "[empty message]"

        logger.info("User message: %s", user_msg[:100])

        # Run the agent in a worker thread because the LangChain agent is
        # blocking and may invoke network I/O internally.
        reply: str = await asyncio.to_thread(_AGENT.run, user_msg)

        logger.info("Bot reply: %s", reply[:100])
    except Exception:  # pragma: no cover – defensive
        # Log *full* traceback for post-mortem debugging.
        logger.exception("Failed to process WhatsApp message")
        reply = (
            "Lo siento, se produjo un error al procesar su solicitud. "
            "Por favor, inténtelo de nuevo más tarde."
        )

    twiml_response = MessagingResponse()
    twiml_response.message(reply)

    # Twilio expects the response body to be XML.
    return Response(content=str(twiml_response), media_type="application/xml")
