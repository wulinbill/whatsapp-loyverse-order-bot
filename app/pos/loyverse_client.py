import time
import asyncio
from typing import Dict, List, Any, Optional
import httpx
from datetime import datetime
import uuid

from ..config import get_settings
from ..logger import get_logger, business_logger
from .loyverse_auth import loyverse_auth

settings = get_settings()
logger = get_logger(__name__)

class LoyverseClient:
    """Loyverse POS系统客户端"""
    
    def __init__(self):
        self.base_url = settings.loyverse_base_url
        self.store_id = settings.loyverse_store_id
        self.pos_device_id = settings.loyverse_pos_device_id
        self.default_payment_type_id = settings.loyverse_default_payment_type_id
        self.tax_rate = settings.tax_rate
    
    async def create_receipt(self, customer_id: str, line_items: List[Dict[str, Any]], user_id: str) -> Dict[str, Any]:
        """
        创建收据/订单
        
        Args:
            customer_id: 客户ID
            line_items: 订单行项目
            user_id: 用户ID（用于日志）
            
        Returns:
            创建的收据信息
        """
        start_time = time.time()
        
        try:
            headers = await loyverse_auth.get_auth_headers()
            
            # 构建收据数据
            receipt_data = self._build_receipt_data(customer_id, line_items)
            
            logger.info(f"Creating receipt for customer {customer_id} with {len(line_items)} items")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/receipts",
                    headers=headers,
                    json=receipt_data,
                    timeout=30.0
                )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                receipt = response.json()
                
                # 记录成功的订单日志
                business_logger.log_pos_order(
                    user_id=user_id,
                    order_id=receipt.get("receipt_number", ""),
                    total_amount=receipt.get("total_money", 0),
                    items_count=len(line_items),
                    duration_ms=duration_ms
                )
                
                logger.info(f"Receipt created successfully: {receipt.get('receipt_number')}")
                return receipt
            else:
                error_msg = f"Failed to create receipt: {response.status_code} - {response.text}"
                business_logger.log_error(
                    user_id=user_id,
                    stage="pos",
                    error_code="RECEIPT_CREATION_FAILED",
                    error_msg=error_msg
                )
                raise Exception(error_msg)
                
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="pos",
                error_code="RECEIPT_CREATION_ERROR",
                error_msg=str(e),
                exception=e
            )
            raise
    
    def _build_receipt_data(self, customer_id: str, line_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """构建收据数据"""
        receipt_data = {
            "store_id": self.store_id,
            "customer_id": customer_id if customer_id else None,
            "source": "whatsapp_bot",
            "receipt_date": datetime.utcnow().isoformat() + "Z",
            "line_items": [],
            "payments": []
        }
        
        # 添加订单行项目
        for item in line_items:
            line_item = {
                "quantity": item.get("quantity", 1),
                "variant_id": item.get("variant_id"),
                "price": item.get("price", 0)
            }
            
            # 添加成本信息（如果有）
            if "cost" in item:
                line_item["cost"] = item["cost"]
            
            # 添加备注（如果有）
            if "note" in item:
                line_item["line_note"] = item["note"]
            
            # 添加税务信息（如果有）
            if "tax_ids" in item:
                line_item["line_taxes"] = [{"id": tax_id} for tax_id in item["tax_ids"]]
            
            # 添加折扣信息（如果有）
            if "discount_ids" in item:
                line_item["line_discounts"] = [{"id": discount_id} for discount_id in item["discount_ids"]]
            
            # 添加修饰符信息（如果有）
            if "modifier_option_ids" in item:
                line_item["line_modifiers"] = [{"modifier_option_id": mod_id} for mod_id in item["modifier_option_ids"]]
            
            receipt_data["line_items"].append(line_item)
        
        # 计算总金额
        subtotal = sum(item.get("price", 0) * item.get("quantity", 1) for item in line_items)
        total_with_tax = subtotal * (1 + self.tax_rate)
        
        # 添加默认支付方式（如果配置了）
        if self.default_payment_type_id:
            receipt_data["payments"].append({
                "payment_type_id": self.default_payment_type_id,
                "money_amount": total_with_tax,
                "paid_at": datetime.utcnow().isoformat() + "Z"
            })
        
        return receipt_data
    
    async def create_customer(self, name: str, phone: str, user_id: str) -> Optional[str]:
        """
        创建客户记录
        
        Args:
            name: 客户姓名
            phone: 客户电话
            user_id: 用户ID（用于日志）
            
        Returns:
            客户ID，如果创建失败返回None
        """
        start_time = time.time()
        
        try:
            headers = await loyverse_auth.get_auth_headers()
            
            customer_data = {
                "name": name,
                "phone_number": phone,
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            
            logger.info(f"Creating customer: {name} ({phone})")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/customers",
                    headers=headers,
                    json=customer_data,
                    timeout=30.0
                )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                customer = response.json()
                customer_id = customer.get("id")
                
                logger.info(f"Customer created successfully: {customer_id}")
                return customer_id
            else:
                error_msg = f"Failed to create customer: {response.status_code} - {response.text}"
                business_logger.log_error(
                    user_id=user_id,
                    stage="pos",
                    error_code="CUSTOMER_CREATION_FAILED",
                    error_msg=error_msg
                )
                logger.error(error_msg)
                return None
                
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="pos",
                error_code="CUSTOMER_CREATION_ERROR",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Exception creating customer: {e}")
            return None
    
    async def find_customer_by_phone(self, phone: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        根据电话号码查找客户
        
        Args:
            phone: 客户电话
            user_id: 用户ID（用于日志）
            
        Returns:
            客户信息，如果未找到返回None
        """
        try:
            headers = await loyverse_auth.get_auth_headers()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/customers",
                    headers=headers,
                    params={"phone_number": phone},
                    timeout=30.0
                )
            
            if response.status_code == 200:
                data = response.json()
                customers = data.get("customers", [])
                
                if customers:
                    logger.info(f"Found existing customer for phone {phone}")
                    return customers[0]  # 返回第一个匹配的客户
                else:
                    logger.info(f"No existing customer found for phone {phone}")
                    return None
            else:
                logger.error(f"Failed to search customers: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            business_logger.log_error(
                user_id=user_id,
                stage="pos",
                error_code="CUSTOMER_SEARCH_ERROR",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Exception searching customer: {e}")
            return None
    
    async def get_receipt(self, receipt_number: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取收据信息
        
        Args:
            receipt_number: 收据号码
            user_id: 用户ID（用于日志）
            
        Returns:
            收据信息，如果未找到返回None
        """
        try:
            headers = await loyverse_auth.get_auth_headers()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/receipts/{receipt_number}",
                    headers=headers,
                    timeout=30.0
                )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get receipt {receipt_number}: {response.status_code}")
                return None
                
        except Exception as e:
            business_logger.log_error(
                user_id=user_id,
                stage="pos",
                error_code="RECEIPT_FETCH_ERROR",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Exception getting receipt: {e}")
            return None
    
    async def update_inventory(self, inventory_updates: List[Dict[str, Any]], user_id: str) -> bool:
        """
        更新库存
        
        Args:
            inventory_updates: 库存更新列表
            user_id: 用户ID（用于日志）
            
        Returns:
            更新是否成功
        """
        try:
            headers = await loyverse_auth.get_auth_headers()
            
            update_data = {"inventory_levels": inventory_updates}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/inventory",
                    headers=headers,
                    json=update_data,
                    timeout=30.0
                )
            
            if response.status_code == 200:
                logger.info(f"Inventory updated successfully for {len(inventory_updates)} items")
                return True
            else:
                logger.error(f"Failed to update inventory: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            business_logger.log_error(
                user_id=user_id,
                stage="pos",
                error_code="INVENTORY_UPDATE_ERROR",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Exception updating inventory: {e}")
            return False
    
    async def test_connection(self) -> bool:
        """测试Loyverse连接"""
        try:
            return await loyverse_auth.test_authentication()
        except Exception as e:
            logger.error(f"Loyverse connection test failed: {e}")
            return False

# 全局Loyverse客户端实例
loyverse_client = LoyverseClient()
