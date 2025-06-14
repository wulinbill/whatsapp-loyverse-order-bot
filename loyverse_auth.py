"""Loyverse OAuth2 自动刷新 Token"""
import os
import httpx
import time
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from utils.logger import get_logger

load_dotenv()

logger = get_logger(__name__)

TOKEN_URL = "https://api.loyverse.com/oauth/token"
CLIENT_ID = os.getenv("LOYVERSE_CLIENT_ID")
CLIENT_SECRET = os.getenv("LOYVERSE_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("LOYVERSE_REFRESH_TOKEN")

if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
    missing = [k for k, v in {
        "LOYVERSE_CLIENT_ID": CLIENT_ID,
        "LOYVERSE_CLIENT_SECRET": CLIENT_SECRET,
        "LOYVERSE_REFRESH_TOKEN": REFRESH_TOKEN,
    }.items() if not v]
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

# 全局 token 状态
_access_token: Optional[str] = None
_expires_at: float = 0.0
_refresh_token: str = REFRESH_TOKEN


@retry(
    stop=stop_after_attempt(3), 
    wait=wait_fixed(2), 
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True
)
async def _refresh() -> None:
    """刷新 OAuth2 访问令牌
    
    使用存储的 refresh_token 获取新的 access_token 和 refresh_token
    
    Raises:
        httpx.HTTPError: HTTP 请求失败
        httpx.TimeoutException: 请求超时
        RuntimeError: 认证服务器返回错误
    """
    global _access_token, _expires_at, _refresh_token
    
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": _refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    
    async with httpx.AsyncClient() as client:
        logger.debug("正在刷新 Loyverse 访问令牌")
        try:
            response = await client.post(TOKEN_URL, data=payload, timeout=15.0)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("Token 刷新失败，HTTP状态码: %d, 响应: %s", 
                        e.response.status_code, e.response.text)
            raise RuntimeError(f"Token refresh failed with status {e.response.status_code}") from e
        except httpx.TimeoutException as e:
            logger.error("Token 刷新超时")
            raise
        
        data: Dict[str, Any] = response.json()
        
        # 验证响应数据
        if "access_token" not in data:
            raise RuntimeError("响应中缺少 access_token")
        
        _access_token = data["access_token"]
        _refresh_token = data.get("refresh_token", _refresh_token)
        expires_in = data.get("expires_in", 3600)  # 默认1小时
        _expires_at = time.time() + expires_in - 60  # 提前60秒刷新

    logger.info("Loyverse 访问令牌已刷新，将在 %d 秒后过期", expires_in)


async def get_access_token() -> str:
    """获取有效的访问令牌
    
    如果当前令牌不存在或即将过期，会自动刷新
    
    Returns:
        有效的 access_token
        
    Raises:
        RuntimeError: 令牌刷新失败
        httpx.HTTPError: 网络请求失败
    """
    if _access_token is None or time.time() >= _expires_at:
        await _refresh()
    
    if _access_token is None:
        raise RuntimeError("无法获取有效的访问令牌")
        
    return _access_token


def get_current_token_info() -> Dict[str, Any]:
    """获取当前令牌信息（用于调试）
    
    Returns:
        包含令牌状态的字典
    """
    return {
        "has_token": _access_token is not None,
        "expires_at": _expires_at,
        "time_until_expiry": max(0, _expires_at - time.time()) if _expires_at > 0 else 0,
        "is_expired": time.time() >= _expires_at if _expires_at > 0 else True
    }
