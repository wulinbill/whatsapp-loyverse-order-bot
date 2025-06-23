#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Loyverse POS API客户端模块
处理与Loyverse点餐系统的集成
"""

import os
import logging
from typing import Dict, Any, List
import httpx
from loyverse_auth import get_access_token

logger = logging.getLogger(__name__)

# Loyverse API基础URL
BASE_URL = "https://api.loyverse.com/v1.0"

# API超时设置
API_TIMEOUT = 15.0

def place_order(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    向Loyverse POS系统下单
    
    Args:
        payload: 订单负载数据
        
    Returns:
        订单响应数据
        
    Raises:
        Exception: 当API调用失败时
    """
    try:
        logger.info("📤 Placing order to Loyverse POS")
        
        # 获取访问令牌
        access_token = get_access_token()
        
        # 构建请求头
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # 获取商店ID
        store_id = os.getenv("LOYVERSE_STORE_ID")
        if not store_id:
            raise ValueError("LOYVERSE_STORE_ID environment variable is required")
        
        # 验证订单负载
        validated_payload = validate_order_payload(payload)
        
        # 构建API端点
        endpoint = f"{BASE_URL}/stores/{store_id}/orders"
        
        logger.debug(f"🔗 API endpoint: {endpoint}")
        logger.debug(f"📦 Order payload: {validated_payload}")
        
        # 发送订单请求
        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.post(
                endpoint,
                json=validated_payload,
                headers=headers
            )
            
            # 检查响应状态
            response.raise_for_status()
            
            # 解析响应数据
            order_data = response.json()
            
            receipt_number = order_data.get("receipt_number", "unknown")
            order_id = order_data.get("id", "unknown")
            
            logger.info(f"✅ Order placed successfully: Receipt #{receipt_number}, ID: {order_id}")
            
            return order_data
            
    except httpx.HTTPStatusError as e:
        error_msg = f"Loyverse API HTTP error: {e.response.status_code}"
        try:
            error_detail = e.response.json()
            error_msg += f" - {error_detail}"
        except:
            error_msg += f" - {e.response.text}"
        
        logger.error(error_msg)
        raise Exception(error_msg)
        
    except httpx.TimeoutException:
        error_msg = "Loyverse API timeout"
        logger.error(error_msg)
        raise Exception(error_msg)
        
    except Exception as e:
        error_msg = f"Failed to place order: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

def validate_order_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证并清理订单负载数据
    
    Args:
        payload: 原始订单负载
        
    Returns:
        验证后的订单负载
        
    Raises:
        ValueError: 当负载数据无效时
    """
    try:
        # 检查必需字段
        if "line_items" not in payload:
            raise ValueError("Missing 'line_items' in order payload")
        
        if "register_id" not in payload:
            register_id = os.getenv("LOYVERSE_REGISTER_ID")
            if not register_id:
                raise ValueError("Missing 'register_id' and LOYVERSE_REGISTER_ID not configured")
            payload["register_id"] = register_id
        
        # 验证行项目
        line_items = payload["line_items"]
        if not isinstance(line_items, list) or len(line_items) == 0:
            raise ValueError("line_items must be a non-empty list")
        
        validated_items = []
        for i, item in enumerate(line_items):
            validated_item = validate_line_item(item, i)
            validated_items.append(validated_item)
        
        # 构建最终负载
        validated_payload = {
            "register_id": payload["register_id"],
            "line_items": validated_items
        }
        
        # 添加可选字段
        optional_fields = ["customer_id", "note", "discount", "tax"]
        for field in optional_fields:
            if field in payload:
                validated_payload[field] = payload[field]
        
        return validated_payload
        
    except Exception as e:
        logger.error(f"Order payload validation failed: {e}")
        raise ValueError(f"Invalid order payload: {str(e)}")

def validate_line_item(item: Dict[str, Any], index: int) -> Dict[str, Any]:
    """
    验证订单行项目
    
    Args:
        item: 行项目数据
        index: 项目索引
        
    Returns:
        验证后的行项目
        
    Raises:
        ValueError: 当项目数据无效时
    """
    required_fields = ["variant_id", "quantity", "price"]
    
    for field in required_fields:
        if field not in item:
            raise ValueError(f"Missing '{field}' in line item {index}")
    
    # 验证数据类型和值
    variant_id = str(item["variant_id"])
    if not variant_id:
        raise ValueError(f"Invalid variant_id in line item {index}")
    
    try:
        quantity = int(item["quantity"])
        if quantity <= 0:
            raise ValueError(f"Quantity must be positive in line item {index}")
    except (ValueError, TypeError):
        raise ValueError(f"Invalid quantity in line item {index}")
    
    try:
        price = float(item["price"])
        if price < 0:
            raise ValueError(f"Price cannot be negative in line item {index}")
    except (ValueError, TypeError):
        raise ValueError(f"Invalid price in line item {index}")
    
    validated_item = {
        "variant_id": variant_id,
        "quantity": quantity,
        "price": int(price * 100)  # 转换为分为单位
    }
    
    # 添加可选字段
    optional_fields = ["modifiers", "note", "discount"]
    for field in optional_fields:
        if field in item:
            validated_item[field] = item[field]
    
    return validated_item

def get_store_info() -> Dict[str, Any]:
    """
    获取商店信息
    
    Returns:
        商店信息字典
    """
    try:
        access_token = get_access_token()
        store_id = os.getenv("LOYVERSE_STORE_ID")
        
        if not store_id:
            raise ValueError("LOYVERSE_STORE_ID not configured")
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        endpoint = f"{BASE_URL}/stores/{store_id}"
        
        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.get(endpoint, headers=headers)
            response.raise_for_status()
            
            store_data = response.json()
            logger.info(f"📍 Retrieved store info: {store_data.get('name', 'Unknown')}")
            
            return store_data
            
    except Exception as e:
        logger.error(f"Failed to get store info: {e}")
        raise Exception(f"Failed to get store info: {str(e)}")

def get_menu_items(limit: int = 100) -> List[Dict[str, Any]]:
    """
    获取菜单项目列表
    
    Args:
        limit: 返回项目数量限制
        
    Returns:
        菜单项目列表
    """
    try:
        access_token = get_access_token()
        store_id = os.getenv("LOYVERSE_STORE_ID")
        
        if not store_id:
            raise ValueError("LOYVERSE_STORE_ID not configured")
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        endpoint = f"{BASE_URL}/stores/{store_id}/items"
        params = {"limit": min(limit, 250)}  # Loyverse API限制
        
        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.get(endpoint, headers=headers, params=params)
            response.raise_for_status()
            
            items_data = response.json()
            items = items_data.get("items", [])
            
            logger.info(f"📜 Retrieved {len(items)} menu items")
            return items
            
    except Exception as e:
        logger.error(f"Failed to get menu items: {e}")
        raise Exception(f"Failed to get menu items: {str(e)}")

def check_api_status() -> Dict[str, Any]:
    """
    检查Loyverse API状态
    
    Returns:
        API状态字典
    """
    try:
        # 检查环境变量
        required_vars = ["LOYVERSE_CLIENT_ID", "LOYVERSE_CLIENT_SECRET", "LOYVERSE_STORE_ID"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            return {
                "status": "unhealthy",
                "error": f"Missing environment variables: {', '.join(missing_vars)}"
            }
        
        # 测试API连接
        access_token = get_access_token()
        store_info = get_store_info()
        
        return {
            "status": "healthy",
            "store_name": store_info.get("name", "Unknown"),
            "store_id": store_info.get("id"),
            "api_version": "v1.0"
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

def cancel_order(order_id: str) -> Dict[str, Any]:
    """
    取消订单
    
    Args:
        order_id: 订单ID
        
    Returns:
        取消结果
    """
    try:
        access_token = get_access_token()
        store_id = os.getenv("LOYVERSE_STORE_ID")
        
        if not store_id:
            raise ValueError("LOYVERSE_STORE_ID not configured")
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        endpoint = f"{BASE_URL}/stores/{store_id}/orders/{order_id}"
        
        # Loyverse通常使用DELETE方法取消订单
        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.delete(endpoint, headers=headers)
            response.raise_for_status()
            
            logger.info(f"🗑️ Order {order_id} cancelled successfully")
            
            return {"status": "cancelled", "order_id": order_id}
            
    except Exception as e:
        logger.error(f"Failed to cancel order {order_id}: {e}")
        raise Exception(f"Failed to cancel order: {str(e)}")

def get_order_history(limit: int = 50) -> List[Dict[str, Any]]:
    """
    获取订单历史
    
    Args:
        limit: 返回订单数量限制
        
    Returns:
        订单历史列表
    """
    try:
        access_token = get_access_token()
        store_id = os.getenv("LOYVERSE_STORE_ID")
        
        if not store_id:
            raise ValueError("LOYVERSE_STORE_ID not configured")
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        endpoint = f"{BASE_URL}/stores/{store_id}/orders"
        params = {"limit": min(limit, 100)}  # API限制
        
        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.get(endpoint, headers=headers, params=params)
            response.raise_for_status()
            
            orders_data = response.json()
            orders = orders_data.get("orders", [])
            
            logger.info(f"📚 Retrieved {len(orders)} order history records")
            return orders
            
    except Exception as e:
        logger.error(f"Failed to get order history: {e}")
        raise Exception(f"Failed to get order history: {str(e)}")