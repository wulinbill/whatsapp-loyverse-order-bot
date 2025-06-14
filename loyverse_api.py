"""Loyverse POS API 封装模块"""
import os
import httpx
import json
from pathlib import Path
from typing import Dict, Any, Optional
from loyverse_auth import get_access_token
from utils.logger import get_logger

logger = get_logger(__name__)

LOYVERSE_API_URL = "https://api.loyverse.com/v1.0"
STORE_ID = os.getenv("LOYVERSE_STORE_ID")

if not STORE_ID:
    raise RuntimeError("Environment variable LOYVERSE_STORE_ID is required but missing.")


async def _get_headers() -> Dict[str, str]:
    """获取 API 请求头
    
    Returns:
        包含授权信息的请求头字典
        
    Raises:
        RuntimeError: 无法获取访问令牌
    """
    token = await get_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


async def get_menu_items(cache_path: str = "menu_data.json") -> Dict[str, Any]:
    """获取菜单项目，优先从缓存读取
    
    Args:
        cache_path: 缓存文件路径
        
    Returns:
        包含菜单项目的字典
        
    Raises:
        httpx.HTTPError: API 请求失败
        json.JSONDecodeError: JSON 解析失败
    """
    cache_file = Path(cache_path)
    
    # 尝试从缓存读取
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            logger.debug("从缓存加载菜单 - %d 个项目", len(cached_data.get("items", [])))
            return cached_data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("缓存文件读取失败: %s，将从 API 重新获取", e)
    else:
        logger.info("菜单缓存不存在，从 Loyverse API 获取")
    
    # 从 API 获取菜单
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{LOYVERSE_API_URL}/items",
                headers=await _get_headers(),
                params={"limit": 250, "deleted": False},
                timeout=15.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("获取菜单失败，HTTP状态码: %d, 响应: %s", 
                        e.response.status_code, e.response.text)
            raise
        except httpx.TimeoutException as e:
            logger.error("获取菜单超时")
            raise
        
        data = response.json()
        
        # 验证响应数据
        if not isinstance(data, dict) or "items" not in data:
            raise ValueError("API 返回的菜单数据格式无效")
        
        # 保存到缓存
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("菜单已缓存 - %d 个项目", len(data.get("items", [])))
        except IOError as e:
            logger.warning("无法保存菜单缓存: %s", e)
        
        return data


async def create_order(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """创建订单
    
    Args:
        order_data: 订单数据字典
        
    Returns:
        包含订单信息的响应字典
        
    Raises:
        httpx.HTTPError: API 请求失败
        ValueError: 订单数据无效
    """
    if not isinstance(order_data, dict):
        raise ValueError("订单数据必须是字典类型")
    
    # 自动注入 store_id
    order_data = order_data.copy()  # 避免修改原始数据
    order_data.setdefault("store_id", STORE_ID)
    
    # 验证必要字段
    if "items" not in order_data or not order_data["items"]:
        raise ValueError("订单必须包含至少一个商品")
    
    logger.debug("创建 Loyverse 订单: %s", json.dumps(order_data, ensure_ascii=False))
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{LOYVERSE_API_URL}/sales",
                headers=await _get_headers(),
                json=order_data,
                timeout=15.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("创建订单失败，HTTP状态码: %d, 响应: %s", 
                        e.response.status_code, e.response.text)
            # 尝试解析错误详情
            try:
                error_detail = e.response.json()
                logger.error("错误详情: %s", error_detail)
            except:
                pass
            raise
        except httpx.TimeoutException as e:
            logger.error("创建订单超时")
            raise
        
        response_data = response.json()
        
        # 验证响应
        if not isinstance(response_data, dict):
            raise ValueError("API 返回的订单数据格式无效")
        
        sale_id = response_data.get("sale_id")
        if sale_id:
            logger.info("订单创建成功 - ID: %s", sale_id)
        else:
            logger.warning("订单创建成功但未返回 sale_id")
        
        return response_data


async def get_store_info() -> Optional[Dict[str, Any]]:
    """获取商店信息（可选功能，用于验证配置）
    
    Returns:
        商店信息字典，失败时返回 None
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{LOYVERSE_API_URL}/stores/{STORE_ID}",
                headers=await _get_headers(),
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.warning("获取商店信息失败: %s", e)
        return None
