#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Loyverse POS API客户端模块 (修复支付类型UUID问题版本)
处理与Loyverse点餐系统的集成
"""

import os
import logging
from typing import Dict, Any, List, Optional
import httpx
from loyverse_auth import get_access_token

logger = logging.getLogger(__name__)

# Loyverse API基础URL
BASE_URL = "https://api.loyverse.com/v1.0"

# API超时设置
API_TIMEOUT = 15.0

def get_payment_types() -> List[Dict[str, Any]]:
    """
    获取商店的支付方式列表
    
    Returns:
        支付方式列表
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
        
        endpoint = f"{BASE_URL}/payment_types"
        params = {"store_id": store_id}
        
        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.get(endpoint, headers=headers, params=params)
            response.raise_for_status()
            
            payment_types_data = response.json()
            payment_types = payment_types_data.get("payment_types", [])
            
            logger.info(f"💳 Retrieved {len(payment_types)} payment types")
            return payment_types
            
    except Exception as e:
        logger.error(f"Failed to get payment types: {e}")
        raise Exception(f"Failed to get payment types: {str(e)}")

def get_default_payment_type_id() -> str:
    """
    获取默认支付方式ID
    
    Returns:
        默认支付方式的UUID
    """
    try:
        # 首先尝试从环境变量获取
        default_payment_id = os.getenv("LOYVERSE_DEFAULT_PAYMENT_TYPE_ID")
        if default_payment_id:
            logger.debug(f"💳 Using payment type from env: {default_payment_id}")
            return default_payment_id
        
        # 如果没有配置，从API获取支付方式
        payment_types = get_payment_types()
        
        if not payment_types:
            raise ValueError("No payment types available")
        
        # 查找现金支付方式
        cash_payment = None
        for payment_type in payment_types:
            name = payment_type.get("name", "").lower()
            payment_type_name = payment_type.get("type", "").lower()
            
            if ("cash" in name or "efectivo" in name or 
                "cash" in payment_type_name or payment_type_name == "cash"):
                cash_payment = payment_type
                break
        
        # 如果找到现金支付，使用它
        if cash_payment:
            payment_id = cash_payment.get("id")
            logger.info(f"💳 Found cash payment type: {cash_payment.get('name')} ({payment_id})")
            return payment_id
        
        # 否则使用第一个可用的支付方式
        first_payment = payment_types[0]
        payment_id = first_payment.get("id")
        logger.warning(f"💳 Using first available payment type: {first_payment.get('name')} ({payment_id})")
        return payment_id
        
    except Exception as e:
        logger.error(f"Failed to get default payment type: {e}")
        # 返回一个示例UUID作为最后备用（需要用户配置正确的）
        raise Exception(f"Cannot determine payment type ID. Please set LOYVERSE_DEFAULT_PAYMENT_TYPE_ID environment variable: {str(e)}")

def place_order(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    向Loyverse POS系统下单 (修复支付类型UUID问题)
    
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
        
        # 验证和修复订单负载
        validated_payload = validate_and_fix_order_payload(payload)
        
        # 构建正确的API端点
        endpoint = f"{BASE_URL}/receipts"
        
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

def validate_and_fix_order_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证并修复订单负载数据 (修复支付类型UUID问题)
    
    Args:
        payload: 原始订单负载
        
    Returns:
        验证并修复后的订单负载
        
    Raises:
        ValueError: 当负载数据无效时
    """
    try:
        # 检查必需字段
        if "line_items" not in payload:
            raise ValueError("Missing 'line_items' in order payload")
        
        # 获取商店ID
        store_id = os.getenv("LOYVERSE_STORE_ID")
        if not store_id:
            raise ValueError("LOYVERSE_STORE_ID environment variable is required")
        
        # 获取POS设备ID
        pos_device_id = payload.get("pos_device_id")
        if not pos_device_id:
            pos_device_id = os.getenv("LOYVERSE_POS_DEVICE_ID")
            if not pos_device_id:
                raise ValueError("Missing 'pos_device_id' and LOYVERSE_POS_DEVICE_ID not configured")
        
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
            "store_id": store_id,
            "pos_device_id": pos_device_id,
            "line_items": validated_items
        }
        
        # 添加支付方式 - 修复UUID问题
        if "payments" not in payload:
            # 计算总金额
            total_amount = sum(item["price"] * item["quantity"] for item in validated_items)
            
            # 获取正确的支付方式ID (UUID)
            payment_type_id = get_default_payment_type_id()
            
            validated_payload["payments"] = [
                {
                    "payment_type_id": payment_type_id,  # 使用正确的UUID
                    "money_amount": total_amount
                }
            ]
            
            logger.info(f"💳 Using payment type ID: {payment_type_id} for amount ${total_amount:.2f}")
        else:
            # 验证现有支付信息
            payments = payload["payments"]
            validated_payments = []
            
            for payment in payments:
                # 确保支付方式ID是有效的UUID
                payment_type_id = payment.get("payment_type_id")
                if not payment_type_id or payment_type_id == "cash":
                    payment_type_id = get_default_payment_type_id()
                
                validated_payment = {
                    "payment_type_id": payment_type_id,
                    "money_amount": payment.get("money_amount", 0.0)
                }
                validated_payments.append(validated_payment)
            
            validated_payload["payments"] = validated_payments
        
        # 添加可选字段
        optional_fields = ["customer_id", "note", "total_discounts", "employee_id"]
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
        "price": price
    }
    
    # 添加可选字段
    optional_fields = ["line_modifiers", "line_note", "line_discounts"]
    for field in optional_fields:
        if field in item:
            validated_item[field] = item[field]
    
    return validated_item

def get_pos_devices() -> List[Dict[str, Any]]:
    """
    获取POS设备列表
    
    Returns:
        POS设备列表
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
        
        endpoint = f"{BASE_URL}/pos_devices"
        params = {"store_id": store_id}
        
        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.get(endpoint, headers=headers, params=params)
            response.raise_for_status()
            
            devices_data = response.json()
            devices = devices_data.get("pos_devices", [])
            
            logger.info(f"📱 Retrieved {len(devices)} POS devices")
            return devices
            
    except Exception as e:
        logger.error(f"Failed to get POS devices: {e}")
        raise Exception(f"Failed to get POS devices: {str(e)}")

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

def check_api_status() -> Dict[str, Any]:
    """
    检查Loyverse API状态
    
    Returns:
        API状态字典
    """
    try:
        # 检查环境变量
        required_vars = ["LOYVERSE_CLIENT_ID", "LOYVERSE_CLIENT_SECRET", "LOYVERSE_STORE_ID", "LOYVERSE_POS_DEVICE_ID"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            return {
                "status": "unhealthy",
                "error": f"Missing environment variables: {', '.join(missing_vars)}"
            }
        
        # 测试API连接
        access_token = get_access_token()
        store_info = get_store_info()
        pos_devices = get_pos_devices()
        
        # 测试支付方式
        try:
            payment_types = get_payment_types()
            default_payment_id = get_default_payment_type_id()
            
            payment_status = {
                "total_payment_types": len(payment_types),
                "default_payment_id": default_payment_id,
                "payment_types_available": True
            }
        except Exception as e:
            payment_status = {
                "payment_types_available": False,
                "payment_error": str(e)
            }
        
        return {
            "status": "healthy",
            "store_name": store_info.get("name", "Unknown"),
            "store_id": store_info.get("id"),
            "pos_devices_count": len(pos_devices),
            "api_version": "v1.0",
            "payment_info": payment_status
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

def setup_payment_type_id():
    """
    设置支付方式ID的辅助函数
    用于初始化时获取和显示可用的支付方式
    
    Returns:
        支付方式信息字典
    """
    try:
        payment_types = get_payment_types()
        
        logger.info("💳 Available payment types:")
        for payment_type in payment_types:
            name = payment_type.get("name", "Unknown")
            payment_id = payment_type.get("id", "Unknown")
            payment_type_name = payment_type.get("type", "Unknown")
            
            logger.info(f"  - {name} ({payment_type_name}): {payment_id}")
        
        # 获取默认支付方式
        default_id = get_default_payment_type_id()
        
        return {
            "available_payment_types": payment_types,
            "default_payment_id": default_id,
            "setup_complete": True
        }
        
    except Exception as e:
        logger.error(f"Failed to setup payment types: {e}")
        return {
            "setup_complete": False,
            "error": str(e),
            "message": "Please configure LOYVERSE_DEFAULT_PAYMENT_TYPE_ID environment variable"
        }
