# WhatsApp Smart Ordering Bot (Claude + Deepgram + Loyverse)

One‑click deployable template for a multilingual, voice‑enabled WhatsApp ordering bot.

* **LLM**: Claude 4 via Anthropic API – natural‑language / multi‑language understanding  
* **ASR**: Deepgram Nova 3 – voice messages → text  
* **Messaging**: Twilio Sandbox for development, 360dialog for production number  
* **POS**: Loyverse POS – OAuth2 automated token refresh + order injection  
* **Menu matching**: local RapidFuzz + PGVector dual recall, zero‑cost matching  
* **Infra**: Docker + Render.com, pluggable database/redis optional  

## Quick start

```bash
git clone <your‑repo>.git
cd whatsapp_order_bot
cp .env.example .env          # fill in keys
docker compose up --build
```

See `docs/DEPLOY.md` for Render deployment steps.