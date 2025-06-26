import time
import asyncio
from typing import Optional, Dict, Any
import httpx
from datetime import datetime, timedelta

from ..config import get_settings
from ..logger import get_logger, business_logger

settings = get_settings()
logger = get_logger(__name__)

class LoyverseAuth:
    """Loyverse OAuth认证管理器"""
    
    def __init__(self):
        self.client_id = settings.loyverse_client_id
        self.client_secret = settings.loyverse_client_secret
        self.refresh_token = settings.loyverse_refresh_token
        self.base_url = settings.loyverse_base_url
        
        # 访问令牌缓存
        self._access_token = None
        self._token_expires_at = None
        self._refresh_lock = asyncio.Lock()
    
    async def get_access_token(self) -> Optional[str]:
        """
        获取有效的访问令牌，自动刷新过期的令牌
        
        Returns:
            有效的访问令牌，如果获取失败返回None
        """
        async with self._refresh_lock:
            # 检查当前令牌是否有效
            if self._is_token_valid():
                return self._access_token
            
            # 刷新令牌
            success = await self._refresh_access_token()
            return self._access_token if success else None
    
    def _is_token_valid(self) -> bool:
        """检查当前令牌是否有效"""
        if not self._access_token or not self._token_expires_at:
            return False
        
        # 提前5分钟刷新令牌
        buffer_time = timedelta(minutes=5)
        return datetime.now() < (self._token_expires_at - buffer_time)
    
    async def _refresh_access_token(self) -> bool:
        """
        刷新访问令牌
        
        Returns:
            刷新是否成功
        """
        start_time = time.time()
        
        try:
            logger.info("Refreshing Loyverse access token...")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url.replace('/v1.0', '')}/oauth/token",
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "refresh_token": self.refresh_token,
                        "grant_type": "refresh_token"
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    timeout=30.0
                )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                token_data = response.json()
                
                # 更新令牌信息
                self._access_token = token_data.get("access_token")
                expires_in = token_data.get("expires_in", 43200)  # 默认12小时
                self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                
                # 更新刷新令牌（如果返回了新的）
                new_refresh_token = token_data.get("refresh_token")
                if new_refresh_token:
                    self.refresh_token = new_refresh_token
                
                business_logger.log_auth_token_refresh(
                    service="loyverse",
                    success=True,
                    duration_ms=duration_ms
                )
                
                logger.info("Loyverse access token refreshed successfully")
                return True
            else:
                error_msg = f"Token refresh failed with status {response.status_code}: {response.text}"
                
                business_logger.log_auth_token_refresh(
                    service="loyverse",
                    success=False,
                    duration_ms=duration_ms,
                    error_msg=error_msg
                )
                
                logger.error(error_msg)
                return False
                
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            
            business_logger.log_auth_token_refresh(
                service="loyverse",
                success=False,
                duration_ms=duration_ms,
                error_msg=error_msg
            )
            
            logger.error(f"Exception during token refresh: {e}")
            return False
    
    async def get_auth_headers(self) -> Dict[str, str]:
        """
        获取包含认证信息的请求头
        
        Returns:
            包含Authorization header的字典
        """
        access_token = await self.get_access_token()
        if not access_token:
            raise Exception("Failed to obtain valid access token")
        
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    
    async def test_authentication(self) -> bool:
        """
        测试认证是否有效
        
        Returns:
            认证是否有效
        """
        try:
            headers = await self.get_auth_headers()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/merchant/",
                    headers=headers,
                    timeout=10.0
                )
            
            if response.status_code == 200:
                logger.info("Loyverse authentication test successful")
                return True
            else:
                logger.error(f"Authentication test failed with status {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Authentication test failed with exception: {e}")
            return False
    
    def get_token_info(self) -> Dict[str, Any]:
        """获取当前令牌信息（用于调试）"""
        return {
            "has_access_token": bool(self._access_token),
            "token_expires_at": self._token_expires_at.isoformat() if self._token_expires_at else None,
            "is_valid": self._is_token_valid(),
            "client_id": self.client_id[:8] + "..." if self.client_id else None
        }

# 全局Loyverse认证实例
loyverse_auth = LoyverseAuth()
