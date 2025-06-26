from pydantic import BaseModel, Field
from functools import lru_cache
import dotenv, os

dotenv.load_dotenv()

class Settings(BaseModel):
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    anthropic_model: str = "claude-3-opus-20240229"
    deepgram_api_key: str = Field(..., alias="DEEPGRAM_API_KEY")
    deepgram_model: str = "nova-3"
    channel_provider: str = "twilio"
    twilio_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_whatsapp_number: str | None = None
    dialog360_token: str | None = None
    dialog360_phone_number: str | None = None
    loyverse_client_id: str
    loyverse_client_secret: str
    loyverse_store_id: str

    class Config:
        case_sensitive = False

@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore