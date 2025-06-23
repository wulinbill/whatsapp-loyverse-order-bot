#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Loyverse API补丁 - 修复KDS显示和税务计算
"""

import os
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

def place_order_with_kds_support(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    向Loyverse下单并确保KDS显示
    
    Args:
        payload: 订单数据，增强了KDS支持
        
    Returns:
        订单响应，包含税后总额
    """
    try:
        from loyverse_api import get_access_token, get_default_payment_type_id, BASE_URL, API_TIMEOUT
        import httpx
        
        logger.info("🍳 Placing order with KDS support")
        
        # 获取必要的配置
        access_token = get_access_token()
        store_id = os.getenv("LOYVERSE_STORE_ID")
        pos_device_id = os.getenv("LOYVERSE_POS_DEVICE_ID")
        
        # 构建完整的订单负载
        order_payload = {
            "store_id": store_id,
            "pos_device_id": pos_device_id,
            "line_items": payload.get("line_items", []),
            # 添加订单来源标识，确保KDS能识别
            "source": "WHATSAPP_BOT",
            "order_type": "TAKEOUT",  # 外卖订单
        }
        
        # 添加客户信息（如果有）
        if "customer_name" in payload:
            order_payload["customer_name"] = payload["customer_name"]
        
        # 添加订单备注，确保在KDS显示
        kitchen_note = payload.get("kitchen_notes", "WhatsApp Order")
        order_note = f"📱 {kitchen_note} - {datetime.now().strftime('%H:%M')}"
        order_payload["note"] = order_note
        
        # 计算税前小计
        subtotal = sum(
            item["price"] * item["quantity"] 
            for item in order_payload["line_items"]
        )
        
        # 计算税额（波多黎各11.5%）
        tax_rate = float(os.getenv("TAX_RATE", "0.115"))
        tax_amount = round(subtotal * tax_rate, 2)
        total_amount = round(subtotal + tax_amount, 2)
        
        # 添加税务信息
        order_payload["total_taxes"] = [{
            "tax_id": os.getenv("LOYVERSE_TAX_ID", "default-tax"),
            "name": "IVU",
            "rate": tax_rate,
            "tax_amount": tax_amount
        }]
        
        # 设置支付信息（包含税后总额）
        payment_type_id = get_default_payment_type_id()
        order_payload["payments"] = [{
            "payment_type_id": payment_type_id,
            "money_amount": total_amount  # 税后总额
        }]
        
        # 添加KDS特定标记
        order_payload["tags"] = ["WHATSAPP", "KDS_PRIORITY"]
        
        # 设置员工ID（如果配置了）
        employee_id = os.getenv("LOYVERSE_EMPLOYEE_ID")
        if employee_id:
            order_payload["employee_id"] = employee_id
        
        logger.debug(f"📋 Order payload with tax: subtotal=${subtotal:.2f}, tax=${tax_amount:.2f}, total=${total_amount:.2f}")
        
        # 发送请求
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        endpoint = f"{BASE_URL}/receipts"
        
        with httpx.Client(timeout=API_TIMEOUT) as client:
            response = client.post(
                endpoint,
                json=order_payload,
                headers=headers
            )
            
            response.raise_for_status()
            
            order_data = response.json()
            
            # 增强响应数据
            order_data["calculated_tax"] = tax_amount
            order_data["calculated_total"] = total_amount
            order_data["kds_sent"] = True
            
            receipt_number = order_data.get("receipt_number", "unknown")
            logger.info(f"✅ Order placed with KDS: Receipt #{receipt_number}, Total: ${total_amount:.2f}")
            
            return order_data
            
    except Exception as e:
        logger.error(f"Failed to place order with KDS: {e}")
        raise

def ensure_kds_visibility(order_id: str) -> bool:
    """
    确保订单在KDS上可见
    
    Args:
        order_id: 订单ID
        
    Returns:
        是否成功
    """
    try:
        from loyverse_api import get_access_token, BASE_URL
        import httpx
        
        access_token = get_access_token()
        
        # 更新订单标签以确保KDS可见性
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # 添加KDS标签
        update_payload = {
            "tags": ["WHATSAPP", "KDS_ACTIVE", "PREPARE_NOW"],
            "kitchen_status": "NEW"
        }
        
        endpoint = f"{BASE_URL}/receipts/{order_id}"
        
        with httpx.Client(timeout=10.0) as client:
            response = client.patch(
                endpoint,
                json=update_payload,
                headers=headers
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Order {order_id} marked for KDS")
                return True
            else:
                logger.warning(f"Failed to update KDS status: {response.status_code}")
                return False
                
    except Exception as e:
        logger.error(f"Error ensuring KDS visibility: {e}")
        return False

def get_order_with_tax_details(receipt_number: str) -> Dict[str, Any]:
    """
    获取订单详情包括税务信息
    
    Args:
        receipt_number: 收据号
        
    Returns:
        订单详情
    """
    try:
        from loyverse_api import get_access_token, BASE_URL
        import httpx
        
        access_token = get_access_token()
        store_id = os.getenv("LOYVERSE_STORE_ID")
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        # 搜索收据
        endpoint = f"{BASE_URL}/receipts"
        params = {
            "store_id": store_id,
            "receipt_number": receipt_number,
            "limit": 1
        }
        
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                endpoint,
                headers=headers,
                params=params
            )
            
            response.raise_for_status()
            
            data = response.json()
            receipts = data.get("receipts", [])
            
            if receipts:
                receipt = receipts[0]
                
                # 提取税务信息
                total_money = receipt.get("total_money", 0)
                total_tax = receipt.get("total_tax", 0)
                subtotal = total_money - total_tax
                
                receipt["tax_details"] = {
                    "subtotal": subtotal,
                    "tax_amount": total_tax,
                    "total_with_tax": total_money,
                    "tax_rate": (total_tax / subtotal) if subtotal > 0 else 0
                }
                
                return receipt
            else:
                logger.warning(f"Receipt {receipt_number} not found")
                return {}
                
    except Exception as e:
        logger.error(f"Error getting order details: {e}")
        return {}

def patch_loyverse_api():
    """
    应用Loyverse API补丁
    """
    try:
        import loyverse_api
        
        # 替换原有的place_order函数
        loyverse_api.place_order = place_order_with_kds_support
        
        # 添加新功能
        loyverse_api.ensure_kds_visibility = ensure_kds_visibility
        loyverse_api.get_order_with_tax_details = get_order_with_tax_details
        
        logger.info("✅ Loyverse API patched for KDS and tax support")
        
    except Exception as e:
        logger.error(f"Failed to patch Loyverse API: {e}")

# 自动应用补丁
patch_loyverse_api()
