from pydantic import BaseModel, Field
from functools import lru_cache
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    # Claude AI配置
    anthropic_api_key: str = Field(..., env="CLAUDE_API_KEY")
    anthropic_model: str = Field(default="claude-4-opus-20250514", env="CLAUDE_MODEL")
    
    # Deepgram语音转文字配置
    deepgram_api_key: str = Field(..., env="DEEPGRAM_API_KEY")
    deepgram_model: str = Field(default="nova-3", env="DEEPGRAM_MODEL")
    
    # WhatsApp配置
    channel_provider: str = Field(default="twilio", env="CHANNEL_PROVIDER")  # twilio or dialog360
    
    # Twilio配置
    twilio_account_sid: str = Field(default="", env="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", env="TWILIO_AUTH_TOKEN")
    twilio_whatsapp_number: str = Field(default="", env="TWILIO_WHATSAPP_NUMBER")
    
    # 360Dialog配置
    dialog360_token: str = Field(default="", env="DIALOG360_TOKEN")
    dialog360_phone_number: str = Field(default="", env="DIALOG360_PHONE_NUMBER")
    
    # Loyverse POS配置
    loyverse_client_id: str = Field(..., env="LOYVERSE_CLIENT_ID")
    loyverse_client_secret: str = Field(..., env="LOYVERSE_CLIENT_SECRET")
    loyverse_refresh_token: str = Field(..., env="LOYVERSE_REFRESH_TOKEN")
    loyverse_store_id: str = Field(..., env="LOYVERSE_STORE_ID")
    loyverse_pos_device_id: str = Field(..., env="LOYVERSE_POS_DEVICE_ID")
    loyverse_default_payment_type_id: str = Field(default="", env="LOYVERSE_DEFAULT_PAYMENT_TYPE_ID")
    loyverse_base_url: str = Field(default="https://api.loyverse.com/v1.0", env="LOYVERSE_BASE_URL")
    
    # OpenAI向量搜索配置
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    openai_embedding_model: str = Field(default="text-embedding-3-small", env="OPENAI_EMBEDDING_MODEL")
    
    # PostgreSQL向量数据库配置
    postgres_host: str = Field(default="localhost", env="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, env="POSTGRES_PORT")
    postgres_db: str = Field(default="whatsapp_bot", env="POSTGRES_DB")
    postgres_user: str = Field(default="postgres", env="POSTGRES_USER")
    postgres_password: str = Field(default="", env="POSTGRES_PASSWORD")
    
    # 应用配置
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    port: int = Field(default=8000, env="PORT")
    environment: str = Field(default="development", env="ENVIRONMENT")
    
    # 业务配置
    restaurant_name: str = Field(default="Kong Food Restaurant", env="RESTAURANT_NAME")
    tax_rate: float = Field(default=0.11, env="TAX_RATE")
    preparation_time_basic: int = Field(default=10, env="PREPARATION_TIME_BASIC")  # 分钟
    preparation_time_complex: int = Field(default=15, env="PREPARATION_TIME_COMPLEX")  # 分钟
    
    # 文本匹配配置
    fuzzy_match_threshold: int = Field(default=80, env="FUZZY_MATCH_THRESHOLD")
    vector_search_threshold: float = Field(default=0.7, env="VECTOR_SEARCH_THRESHOLD")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    return Settings()
