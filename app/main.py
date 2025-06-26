from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from .logger import get_logger
from .config import get_settings

logger = get_logger(__name__)
settings = get_settings()

app = FastAPI(title="WhatsApp Ordering Bot")

@app.get("/health")
async def health():
    return {"status":"ok"}

# --- place holder routes ---
@app.post("/webhook/whatsapp")
async def whatsapp_webhook(payload: dict):
    logger.info("incoming message %s", payload)
    # TODO: invoke Deepgram / Claude / matcher / pos flow
    return JSONResponse(content={"status":"accepted"}, status_code=202)