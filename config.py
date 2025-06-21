"""配置管理模块"""
import os
from typing import Optional
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """应用配置类"""
    
    # OpenAI 配置
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o", env="OPENAI_MODEL")
    openai_temperature: float = Field(0.1, env="OPENAI_TEMPERATURE")
    openai_max_tokens: int = Field(1500, env="OPENAI_MAX_TOKENS")
    openai_timeout: float = Field(30.0, env="OPENAI_TIMEOUT")
    
    # Loyverse 配置
    loyverse_client_id: str = Field(..., env="LOYVERSE_CLIENT_ID")
    loyverse_client_secret: str = Field(..., env="LOYVERSE_CLIENT_SECRET")
    loyverse_refresh_token: str = Field(..., env="LOYVERSE_REFRESH_TOKEN")
    loyverse_store_id: str = Field(..., env="LOYVERSE_STORE_ID")
    loyverse_api_url: str = Field("https://api.loyverse.com/v1.0", env="LOYVERSE_API_URL")
    
    # 缓存配置
    menu_cache_ttl: int = Field(600, env="MENU_CACHE_TTL")  # 10分钟
    session_ttl: int = Field(3600, env="SESSION_TTL")  # 1小时
    
    # 业务配置
    default_prep_time_minutes: int = Field(10, env="DEFAULT_PREP_TIME_MINUTES")
    large_order_prep_time_minutes: int = Field(15, env="LARGE_ORDER_PREP_TIME_MINUTES")
    large_order_threshold: int = Field(3, env="LARGE_ORDER_THRESHOLD")
    max_message_length: int = Field(1000, env="MAX_MESSAGE_LENGTH")
    
    # WhatsApp 配置
    twilio_auth_token: Optional[str] = Field(None, env="TWILIO_AUTH_TOKEN")
    webhook_validation_enabled: bool = Field(False, env="WEBHOOK_VALIDATION_ENABLED")
    
    # 系统配置
    log_level: str = Field("INFO", env="LOG_LEVEL")
    debug_mode: bool = Field(False, env="DEBUG_MODE")
    cleanup_interval: int = Field(50, env="CLEANUP_INTERVAL")
    
    # FastAPI 配置
    app_host: str = Field("0.0.0.0", env="APP_HOST")
    app_port: int = Field(8000, env="APP_PORT")
    app_reload: bool = Field(False, env="APP_RELOAD")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# 全局配置实例
settings = Settings()


def get_settings() -> Settings:
    """获取配置实例"""
    return settings


def validate_required_settings() -> list[str]:
    """验证必需的配置项，返回缺失的配置列表"""
    missing = []
    
    required_fields = [
        ("openai_api_key", "OPENAI_API_KEY"),
        ("loyverse_client_id", "LOYVERSE_CLIENT_ID"),
        ("loyverse_client_secret", "LOYVERSE_CLIENT_SECRET"),
        ("loyverse_refresh_token", "LOYVERSE_REFRESH_TOKEN"),
        ("loyverse_store_id", "LOYVERSE_STORE_ID"),
    ]
    
    for field_name, env_name in required_fields:
        value = getattr(settings, field_name, None)
        if not value:
            missing.append(env_name)
    
    return missing


def print_config_summary():
    """打印配置摘要（隐藏敏感信息）"""
    print("=" * 50)
    print("配置摘要:")
    print(f"  OpenAI 模型: {settings.openai_model}")
    print(f"  OpenAI Temperature: {settings.openai_temperature}")
    print(f"  缓存TTL: {settings.menu_cache_ttl}秒")
    print(f"  会话TTL: {settings.session_ttl}秒")
    print(f"  日志级别: {settings.log_level}")
    print(f"  调试模式: {settings.debug_mode}")
    print(f"  最大消息长度: {settings.max_message_length}")
    print(f"  默认准备时间: {settings.default_prep_time_minutes}分钟")
    print(f"  大订单准备时间: {settings.large_order_prep_time_minutes}分钟")
    print(f"  大订单阈值: {settings.large_order_threshold}个菜品")
    
    # 检查敏感配置是否存在（不显示具体值）
    sensitive_configs = [
        ("OpenAI API Key", bool(settings.openai_api_key)),
        ("Loyverse Client ID", bool(settings.loyverse_client_id)),
        ("Loyverse Client Secret", bool(settings.loyverse_client_secret)),
        ("Loyverse Refresh Token", bool(settings.loyverse_refresh_token)),
        ("Loyverse Store ID", bool(settings.loyverse_store_id)),
    ]
    
    print("  敏感配置状态:")
    for name, is_set in sensitive_configs:
        status = "✅ 已配置" if is_set else "❌ 未配置"
        print(f"    {name}: {status}")
    
    print("=" * 50)


# 常量定义（从配置派生）
class Constants:
    """应用常量"""
    
    # 订单状态
    ORDER_STAGE_GREETING = "GREETING"
    ORDER_STAGE_CAPTURE = "CAPTURE"
    ORDER_STAGE_NAME = "NAME"
    ORDER_STAGE_CONFIRM = "CONFIRM"
    ORDER_STAGE_DONE = "DONE"
    
    # 终止关键词
    TERMINATION_KEYWORDS = {"no", "nada", "eso es todo", "listo", "ya", "terminar", "finalizar"}
    
    # 响应模板
    ERROR_MESSAGES = {
        "es": "Lo siento, hubo un error al procesar su pedido. Por favor, inténtelo de nuevo más tarde.",
        "en": "Sorry, there was an error processing your order. Please try again later.",
        "zh": "抱歉，处理您的订单时出现错误。请稍后再试。"
    }
    
    GREETING_MESSAGE = "Hola, restaurante KongFood. ¿Qué desea ordenar hoy?"
    NAME_REQUEST_MESSAGE = "Para finalizar, ¿podría indicarme su nombre, por favor?"
    CLARIFICATION_MESSAGE = "Disculpe, ¿podría aclararlo, por favor?"
    EMPTY_ORDER_MESSAGE = "Aún no tengo ningún plato registrado. ¿Podría indicarme qué desea?"
    THANK_YOU_MESSAGE = "¡Muchas gracias! Si desea hacer otra orden, dígame por favor."


constants = Constants()
