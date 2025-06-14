from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
from utils.logger import get_logger
from whatsapp_handler import handle_whatsapp_message

# Load environment variables from .env at startup
load_dotenv()

logger = get_logger(__name__)

app = FastAPI()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# Health-check – useful for deploys and uptime monitors

@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:  # pragma: no cover – trivial
    """Lightweight endpoint used by orchestrators to verify the app is alive."""
    return "OK"

@app.post("/whatsapp-webhook")
async def whatsapp_webhook(request: Request):
    """Entry point for Twilio WhatsApp webhook messages."""
    logger.debug("Incoming WhatsApp webhook")
    return await handle_whatsapp_message(request)
