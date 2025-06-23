#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Loyverse OAuth认证模块 (修复权限问题版本)
处理访问令牌的获取、刷新和存储
"""

import os
import json
import time
import logging
import pathlib
import tempfile
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

# 修复权限问题：使用临时目录或环境变量指定的路径
def get_token_storage_path() -> pathlib.Path:
    """获取令牌存储路径，优先使用环境变量，否则使用临时目录"""
    storage_dir = os.getenv("TOKEN_STORAGE_PATH")
    if storage_dir:
        # 使用环境变量指定的路径
        base_path = pathlib.Path(storage_dir)
    else:
        # 使用系统临时目录
        base_path = pathlib.Path(tempfile.gettempdir())
    
    return base_path / "loyverse_token.json"

# 动态获取令牌文件路径
TOKEN_FILE = get_token_storage_path()

# OAuth端点
OAUTH_TOKEN_URL = "https://api.loyverse.com/oauth/token"

# API超时设置
AUTH_TIMEOUT = 15.0

def save_token(token_data: Dict[str, Any]) -> None:
    """
    保存令牌数据到文件 (修复权限问题版本)
    
    Args:
        token_data: 令牌数据字典
    """
    try:
        # 重新获取当前路径 (可能环境变量已更新)
        current_token_file = get_token_storage_path()
        
        # 确保父目录存在
        parent_dir = current_token_file.parent
        if not parent_dir.exists():
            try:
                parent_dir.mkdir(parents=True, exist_ok=True)
                logger.debug(f"📁 Created directory: {parent_dir}")
            except PermissionError:
                # 如果创建失败，尝试使用临时目录
                temp_dir = pathlib.Path(tempfile.gettempdir())
                current_token_file = temp_dir / "loyverse_token.json"
                logger.warning(f"⚠️ Permission denied, using temp file: {current_token_file}")
        
        # 写入令牌数据
        with open(current_token_file, 'w', encoding='utf-8') as f:
            json.dump(token_data, f, indent=2)
        
        # 尝试设置文件权限（如果支持）
        try:
            current_token_file.chmod(0o600)
        except (OSError, AttributeError):
            # 在某些系统上可能不支持chmod
            logger.debug("⚠️ Cannot set file permissions (not supported)")
        
        logger.debug(f"💾 Token saved successfully to: {current_token_file}")
        
        # 更新全局TOKEN_FILE变量
        global TOKEN_FILE
        TOKEN_FILE = current_token_file
        
    except Exception as e:
        logger.error(f"Failed to save token: {e}")
        # 尝试最后的备用方案：内存存储
        try:
            _store_token_in_memory(token_data)
            logger.warning("💾 Token stored in memory as fallback")
        except:
            raise Exception(f"Failed to save token: {str(e)}")

def load_token() -> Dict[str, Any]:
    """
    从文件加载令牌数据 (修复权限问题版本)
    
    Returns:
        令牌数据字典，如果文件不存在返回空字典
    """
    try:
        # 重新获取当前路径
        current_token_file = get_token_storage_path()
        
        # 检查全局TOKEN_FILE是否存在且不同
        if TOKEN_FILE != current_token_file and TOKEN_FILE.exists():
            current_token_file = TOKEN_FILE
        
        if current_token_file.exists():
            with open(current_token_file, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
            logger.debug(f"📖 Token loaded from: {current_token_file}")
            return token_data
        else:
            # 尝试从内存加载
            memory_token = _load_token_from_memory()
            if memory_token:
                logger.debug("📖 Token loaded from memory")
                return memory_token
            
            logger.debug(f"📄 No token file found at: {current_token_file}")
            return {}
            
    except json.JSONDecodeError as e:
        logger.error(f"Token file corrupted: {e}")
        # 删除损坏的文件
        try:
            current_token_file = get_token_storage_path()
            if current_token_file.exists():
                current_token_file.unlink()
        except:
            pass
        return {}
        
    except Exception as e:
        logger.error(f"Failed to load token: {e}")
        # 尝试从内存加载
        memory_token = _load_token_from_memory()
        if memory_token:
            return memory_token
        return {}

# 内存存储备用方案
_memory_token_storage = {}

def _store_token_in_memory(token_data: Dict[str, Any]) -> None:
    """在内存中存储令牌作为备用方案"""
    global _memory_token_storage
    _memory_token_storage = token_data.copy()

def _load_token_from_memory() -> Dict[str, Any]:
    """从内存加载令牌"""
    return _memory_token_storage.copy()

def refresh_access_token() -> str:
    """
    刷新访问令牌
    
    Returns:
        新的访问令牌
        
    Raises:
        Exception: 当刷新失败时
    """
    try:
        logger.info("🔄 Refreshing Loyverse access token")
        
        # 获取刷新令牌
        refresh_token = get_refresh_token()
        if not refresh_token:
            raise ValueError("No refresh token available")
        
        # 获取OAuth配置
        client_id = os.getenv("LOYVERSE_CLIENT_ID")
        client_secret = os.getenv("LOYVERSE_CLIENT_SECRET")
        
        if not client_id or not client_secret:
            raise ValueError("Missing OAuth credentials (LOYVERSE_CLIENT_ID or LOYVERSE_CLIENT_SECRET)")
        
        # 构建请求数据
        token_request_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret
        }
        
        logger.debug(f"🌐 Requesting token from {OAUTH_TOKEN_URL}")
        
        # 发送请求
        with httpx.Client(timeout=AUTH_TIMEOUT) as client:
            response = client.post(
                OAUTH_TOKEN_URL,
                data=token_request_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            response.raise_for_status()
            
            # 解析响应
            token_data = response.json()
            
            # 验证响应数据
            if "access_token" not in token_data:
                raise ValueError("No access_token in response")
            
            # 计算过期时间
            expires_in = token_data.get("expires_in", 3500)  # 默认接近1小时
            token_data["expires_at"] = int(time.time()) + expires_in - 60  # 提前1分钟
            
            # 保存新令牌
            save_token(token_data)
            
            access_token = token_data["access_token"]
            logger.info(f"✅ Access token refreshed successfully (expires in {expires_in}s)")
            
            return access_token
            
    except httpx.HTTPStatusError as e:
        error_msg = f"OAuth HTTP error: {e.response.status_code}"
        try:
            error_detail = e.response.json()
            error_msg += f" - {error_detail}"
        except:
            error_msg += f" - {e.response.text}"
        
        logger.error(error_msg)
        raise Exception(error_msg)
        
    except httpx.TimeoutException:
        error_msg = "OAuth request timeout"
        logger.error(error_msg)
        raise Exception(error_msg)
        
    except Exception as e:
        error_msg = f"Failed to refresh token: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

def get_refresh_token() -> Optional[str]:
    """
    获取刷新令牌
    
    Returns:
        刷新令牌，优先从环境变量获取，然后从文件获取
    """
    # 优先使用环境变量中的刷新令牌
    refresh_token = os.getenv("LOYVERSE_REFRESH_TOKEN")
    if refresh_token:
        logger.debug("🔑 Using refresh token from environment")
        return refresh_token
    
    # 从文件获取
    token_data = load_token()
    refresh_token = token_data.get("refresh_token")
    if refresh_token:
        logger.debug("🔑 Using refresh token from file")
        return refresh_token
    
    logger.warning("⚠️ No refresh token found")
    return None

def get_access_token() -> str:
    """
    获取有效的访问令牌
    如果当前令牌即将过期或已过期，会自动刷新
    
    Returns:
        有效的访问令牌
        
    Raises:
        Exception: 当无法获取令牌时
    """
    try:
        # 加载现有令牌
        token_data = load_token()
        
        # 检查令牌是否有效
        if is_token_valid(token_data):
            access_token = token_data["access_token"]
            logger.debug("✅ Using existing valid access token")
            return access_token
        
        # 令牌无效或即将过期，需要刷新
        logger.info("🔄 Access token expired or invalid, refreshing...")
        return refresh_access_token()
        
    except Exception as e:
        logger.error(f"Failed to get access token: {e}")
        raise Exception(f"Failed to get access token: {str(e)}")

def is_token_valid(token_data: Dict[str, Any]) -> bool:
    """
    检查令牌是否有效
    
    Args:
        token_data: 令牌数据
        
    Returns:
        令牌是否有效
    """
    if not token_data:
        return False
    
    # 检查必要字段
    if "access_token" not in token_data or "expires_at" not in token_data:
        return False
    
    # 检查是否过期（提前60秒判断）
    current_time = int(time.time())
    expires_at = token_data.get("expires_at", 0)
    
    if current_time >= expires_at:
        logger.debug("⏰ Token expired or expiring soon")
        return False
    
    # 计算剩余时间
    remaining_time = expires_at - current_time
    logger.debug(f"⏳ Token valid for {remaining_time} more seconds")
    
    return True

def revoke_token() -> bool:
    """
    撤销当前令牌
    
    Returns:
        是否成功撤销
    """
    try:
        token_data = load_token()
        access_token = token_data.get("access_token")
        
        if not access_token:
            logger.info("🚫 No token to revoke")
            return True
        
        # 删除本地令牌文件
        try:
            current_token_file = get_token_storage_path()
            if current_token_file.exists():
                current_token_file.unlink()
                logger.info("🗑️ Local token file deleted")
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"Could not delete token file: {e}")
        
        # 清除内存存储
        global _memory_token_storage
        _memory_token_storage = {}
        
        logger.info("✅ Token revoked successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to revoke token: {e}")
        return False

def get_token_info() -> Dict[str, Any]:
    """
    获取令牌信息（用于调试和监控）
    
    Returns:
        令牌信息字典
    """
    try:
        token_data = load_token()
        current_token_file = get_token_storage_path()
        
        if not token_data:
            return {
                "status": "no_token",
                "file_path": str(current_token_file),
                "has_file": current_token_file.exists(),
                "has_env_refresh_token": bool(os.getenv("LOYVERSE_REFRESH_TOKEN")),
                "has_memory_token": bool(_memory_token_storage)
            }
        
        current_time = int(time.time())
        expires_at = token_data.get("expires_at", 0)
        remaining_time = max(0, expires_at - current_time)
        
        return {
            "status": "valid" if is_token_valid(token_data) else "expired",
            "has_access_token": bool(token_data.get("access_token")),
            "has_refresh_token": bool(token_data.get("refresh_token")),
            "expires_at": expires_at,
            "remaining_seconds": remaining_time,
            "file_path": str(current_token_file),
            "file_exists": current_token_file.exists(),
            "storage_method": "file" if current_token_file.exists() else "memory"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

def initialize_oauth_from_env() -> bool:
    """
    从环境变量初始化OAuth令牌
    用于首次设置或重置令牌
    
    Returns:
        是否成功初始化
    """
    try:
        refresh_token = os.getenv("LOYVERSE_REFRESH_TOKEN")
        if not refresh_token:
            logger.warning("⚠️ LOYVERSE_REFRESH_TOKEN not found in environment")
            return False
        
        # 创建初始令牌数据
        initial_token_data = {
            "refresh_token": refresh_token,
            "expires_at": 0  # 强制刷新
        }
        
        save_token(initial_token_data)
        logger.info("🎯 OAuth initialized from environment variables")
        
        # 立即获取访问令牌
        get_access_token()
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize OAuth from environment: {e}")
        return False

def test_token_storage() -> Dict[str, Any]:
    """
    测试令牌存储功能
    
    Returns:
        测试结果
    """
    try:
        test_data = {
            "test": "token_storage_test",
            "timestamp": int(time.time())
        }
        
        # 测试保存
        save_token(test_data)
        
        # 测试加载
        loaded_data = load_token()
        
        # 验证数据
        success = loaded_data.get("test") == "token_storage_test"
        
        # 清理测试数据
        if success:
            revoke_token()
        
        return {
            "success": success,
            "storage_path": str(get_token_storage_path()),
            "loaded_data": loaded_data
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "storage_path": str(get_token_storage_path())
        }
