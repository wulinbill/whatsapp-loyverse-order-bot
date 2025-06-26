from pydantic import Field
from pydantic_settings import BaseSettings
from functools import lru_cache
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

class Settings(BaseSettings):
    """应用配置设置 - 纯内存版本（无数据库）"""
    
    # ========================================================================
    # Claude AI配置
    # ========================================================================
    anthropic_api_key: str = Field(
        description="Anthropic Claude API Key"
    )
    anthropic_model: str = Field(
        default="claude-4-sonnet-20250514",
        description="Claude model to use"
    )
    
    # ========================================================================
    # Deepgram语音转文字配置
    # ========================================================================
    deepgram_api_key: str = Field(
        description="Deepgram API Key for speech-to-text"
    )
    deepgram_model: str = Field(
        default="nova-3",
        description="Deepgram model to use"
    )
    
    # ========================================================================
    # WhatsApp配置
    # ========================================================================
    channel_provider: str = Field(
        default="twilio",
        description="WhatsApp provider: twilio or dialog360"
    )
    
    # ========================================================================
    # Twilio配置
    # ========================================================================
    twilio_account_sid: str = Field(
        default="",
        description="Twilio Account SID"
    )
    twilio_auth_token: str = Field(
        default="",
        description="Twilio Auth Token"
    )
    twilio_whatsapp_number: str = Field(
        default="",
        description="Twilio WhatsApp number (e.g., whatsapp:+14155238886)"
    )
    
    # ========================================================================
    # 360Dialog配置
    # ========================================================================
    dialog360_token: str = Field(
        default="",
        description="360Dialog API token"
    )
    dialog360_phone_number: str = Field(
        default="",
        description="360Dialog phone number"
    )
    
    # ========================================================================
    # Loyverse POS配置
    # ========================================================================
    loyverse_client_id: str = Field(
        description="Loyverse OAuth Client ID"
    )
    loyverse_client_secret: str = Field(
        description="Loyverse OAuth Client Secret"
    )
    loyverse_refresh_token: str = Field(
        description="Loyverse OAuth Refresh Token"
    )
    loyverse_store_id: str = Field(
        description="Loyverse Store ID"
    )
    loyverse_pos_device_id: str = Field(
        description="Loyverse POS Device ID"
    )
    loyverse_default_payment_type_id: str = Field(
        default="",
        description="Default payment type ID in Loyverse"
    )
    loyverse_base_url: str = Field(
        default="https://api.loyverse.com/v1.0",
        description="Loyverse API base URL"
    )
    
    # ========================================================================
    # OpenAI向量搜索配置（可选）
    # ========================================================================
    openai_api_key: str = Field(
    default="",
    description="OpenAI API Key for embeddings (optional - not required)"
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model"
    )
    
    # ========================================================================
    # 应用配置
    # ========================================================================
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    port: int = Field(
        default=8000,
        description="Application port"
    )
    environment: str = Field(
        default="development",
        description="Application environment"
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode"
    )
    
    # ========================================================================
    # 业务配置
    # ========================================================================
    restaurant_name: str = Field(
        default="Kong Food Restaurant",
        description="Restaurant name"
    )
    tax_rate: float = Field(
        default=0.11,
        description="Tax rate (e.g., 0.11 for 11%)"
    )
    preparation_time_basic: int = Field(
        default=10,
        description="Basic dish preparation time in minutes"
    )
    preparation_time_complex: int = Field(
        default=15,
        description="Complex dish preparation time in minutes"
    )
    
    # 营业时间
    business_hours_start: str = Field(
        default="09:00",
        description="Business hours start time (HH:MM)"
    )
    business_hours_end: str = Field(
        default="22:00",
        description="Business hours end time (HH:MM)"
    )
    
    # 货币和地区
    currency: str = Field(
        default="USD",
        description="Currency code"
    )
    timezone: str = Field(
        default="America/New_York",
        description="Timezone"
    )
    
    # ========================================================================
    # AI和搜索配置
    # ========================================================================
    fuzzy_match_threshold: int = Field(
        default=80,
        description="Fuzzy matching threshold (0-100)"
    )
    vector_search_threshold: float = Field(
        default=0.7,
        description="Vector search similarity threshold (0.0-1.0)"
    )
    max_search_results: int = Field(
        default=5,
        description="Maximum number of search results to return"
    )
    
    # ========================================================================
    # 功能开关
    # ========================================================================
    enable_voice_messages: bool = Field(
        default=True,
        description="Enable voice message processing"
    )
    enable_vector_search: bool = Field(
        default=False,
        description="Enable vector-based menu search"
    )
    enable_analytics: bool = Field(
        default=True,
        description="Enable analytics and logging"
    )
    enable_cache: bool = Field(
        default=True,
        description="Enable response caching"
    )
    
    # ========================================================================
    # 内存存储配置（替代数据库）
    # ========================================================================
    session_cleanup_interval: int = Field(
        default=300,  # 5 minutes
        description="Session cleanup interval in seconds"
    )
    max_sessions_in_memory: int = Field(
        default=1000,
        description="Maximum number of sessions to keep in memory"
    )
    session_timeout_seconds: int = Field(
        default=3600,  # 1 hour
        description="Session timeout in seconds"
    )
    
    # ========================================================================
    # 缓存和性能配置
    # ========================================================================
    cache_ttl_seconds: int = Field(
        default=300,  # 5 minutes
        description="Cache TTL in seconds"
    )
    max_message_length: int = Field(
        default=4096,
        description="Maximum message length"
    )
    rate_limit_per_minute: int = Field(
        default=30,
        description="Rate limit per user per minute"
    )
    
    # ========================================================================
    # Pydantic配置
    # ========================================================================
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",  # 忽略额外的环境变量
        "validate_assignment": True,  # 验证赋值
    }

    def __init__(self, **kwargs):
        """初始化设置，支持从环境变量读取"""
        super().__init__(**kwargs)
        
        # 验证必需的配置
        self._validate_required_settings()
    
    def _validate_required_settings(self):
        """验证必需的配置项"""
        required_for_production = [
            "anthropic_api_key",
            "deepgram_api_key",
            "loyverse_client_id",
            "loyverse_client_secret",
            "loyverse_refresh_token",
            "loyverse_store_id",
            "loyverse_pos_device_id"
        ]
        
        if self.environment == "production":
            missing = []
            for field in required_for_production:
                value = getattr(self, field, None)
                if not value or value in ["", "placeholder", "your-key-here"]:
                    missing.append(field.upper())
            
            if missing:
                raise ValueError(f"Missing required environment variables for production: {', '.join(missing)}")
    
    @property
    def is_production(self) -> bool:
        """检查是否为生产环境"""
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """检查是否为开发环境"""
        return self.environment.lower() == "development"
    
    def get_cors_origins(self) -> list[str]:
        """获取CORS允许的源"""
        if self.is_development:
            return ["*"]
        else:
            # 生产环境应该指定具体的域名
            return [
                "https://your-frontend-domain.com",
                "https://your-admin-panel.com"
            ]
    
    # ========================================================================
    # 内存存储辅助方法
    # ========================================================================
    
    def should_use_memory_storage(self) -> bool:
        """确认使用内存存储"""
        return True  # 始终使用内存存储
    
    def get_session_config(self) -> dict:
        """获取会话配置"""
        return {
            "cleanup_interval": self.session_cleanup_interval,
            "max_sessions": self.max_sessions_in_memory,
            "timeout": self.session_timeout_seconds
        }

# ========================================================================
# 全局设置实例
# ========================================================================
@lru_cache()
def get_settings() -> Settings:
    """获取应用设置（带缓存）"""
    return Settings()

# 导出常用的设置实例
settings = get_settings()
