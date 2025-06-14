from fastapi import FastAPI, Request
from whatsapp_handler import handle_whatsapp_message

app = FastAPI()

@app.post("/whatsapp-webhook")
async def whatsapp_webhook(request: Request):
    return await handle_whatsapp_message(request)
