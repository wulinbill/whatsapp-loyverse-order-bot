import os
from typing import Optional, List
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """应用配置设置"""
    
    # 基本应用设置
    app_name: str = "Kong Food Bot"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False)
    
    # 餐厅信息
    restaurant_name: str = Field(default="Kong Food")
    
    # 数据库设置
    database_url: str = Field(...)
    
    # Loyverse POS API 设置 (OAuth 2.0)
    loyverse_refresh_token: str = Field(..., description="Loyverse OAuth Refresh Token")
    loyverse_client_id: str = Field(..., description="Loyverse OAuth Client ID")
    loyverse_client_secret: str = Field(..., description="Loyverse OAuth Client Secret")
    loyverse_store_id: str = Field(...)
    loyverse_base_url: str = Field(default="https://api.loyverse.com/v1.0")
    
    # 税费设置
    tax_rate: float = Field(default=0.115)  # IVU 11.5%
    
    # Claude AI 设置
    claude_api_key: str = Field(...)
    claude_model: str = Field(default="claude-3-sonnet-20240229")
    
    # Deepgram 语音识别设置
    deepgram_api_key: str = Field(...)
    
    # WhatsApp 提供商设置
    channel_provider: str = Field(default="twilio")  # "twilio" 或 "dialog360"
    
    # Twilio 设置
    twilio_account_sid: Optional[str] = Field(default=None)
    twilio_auth_token: Optional[str] = Field(default=None)
    twilio_phone_number: Optional[str] = Field(default=None)
    
    # 360Dialog 设置
    dialog360_api_key: Optional[str] = Field(default=None)
    dialog360_base_url: Optional[str] = Field(default="https://waba.360dialog.io")
    
    # 模糊匹配设置
    fuzzy_match_threshold: int = Field(default=80)
    
    # 向量搜索设置
    vector_search_enabled: bool = Field(default=True)
    embedding_model: str = Field(default="text-embedding-3-small")
    
    # API 限制设置
    rate_limit_requests: int = Field(default=100)
    rate_limit_window: int = Field(default=3600)  # 1 hour
    
    # 日志设置
    log_level: str = Field(default="INFO")
    log_file: Optional[str] = Field(default=None)
    
    # Redis 设置（用于会话管理）
    redis_url: Optional[str] = Field(default=None)
    
    # Webhook 设置
    webhook_secret: Optional[str] = Field(default=None)
    webhook_verify_token: Optional[str] = Field(default=None)
    
    # 文件上传设置
    max_file_size: int = Field(default=10485760)  # 10MB
    upload_directory: str = Field(default="uploads")
    
    # 会话超时设置
    session_timeout_minutes: int = Field(default=60)
    
    # 安全设置
    secret_key: str = Field(...)
    allowed_hosts: List[str] = Field(default=["*"])
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }

# 全局设置实例
_settings = None

def get_settings() -> Settings:
    """获取应用设置的单例实例"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

# 验证必要的配置
def validate_settings():
    """验证必要的配置是否存在"""
    settings = get_settings()
    
    required_settings = [
        ("loyverse_refresh_token", "Loyverse Refresh Token"),
        ("loyverse_client_id", "Loyverse Client ID"),
        ("loyverse_client_secret", "Loyverse Client Secret"),
        ("loyverse_store_id", "Loyverse Store ID"),
        ("claude_api_key", "Claude API Key"),
        ("deepgram_api_key", "Deepgram API Key"),
        ("database_url", "Database URL"),
        ("secret_key", "Secret Key")
    ]
    
    missing_settings = []
    
    for setting_name, display_name in required_settings:
        value = getattr(settings, setting_name, None)
        if not value:
            missing_settings.append(display_name)
    
    if missing_settings:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_settings)}")
    
    # 验证 WhatsApp 提供商配置
    if settings.channel_provider == "twilio":
        if not all([settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_phone_number]):
            raise ValueError("Twilio configuration incomplete. Need TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER")
    
    elif settings.channel_provider == "dialog360":
        if not settings.dialog360_api_key:
            raise ValueError("360Dialog configuration incomplete. Need DIALOG360_API_KEY")
    
    return True
