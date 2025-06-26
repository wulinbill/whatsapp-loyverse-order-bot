import asyncio
import aiohttp
import json
from typing import Dict, List, Any, Optional
from datetime import datetime

from ..config import get_settings
from ..logger import get_logger, business_logger

settings = get_settings()
logger = get_logger(__name__)

class LoyverseClient:
    """Loyverse POS API客户端 - 支持正确的税费处理"""
    
    def __init__(self):
        self.api_token = settings.loyverse_api_token
        self.base_url = "https://api.loyverse.com/v1.0"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
    
    async def create_receipt_with_taxes(self, receipt_data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """
        创建包含正确税费的收据
        
        Args:
            receipt_data: 收据数据，包含taxes字段
            user_id: 用户ID
            
        Returns:
            创建的收据信息
        """
        try:
            # 获取税费ID（需要预先配置在Loyverse中）
            tax_id = await self._get_ivu_tax_id(user_id)
            
            # 构建完整的收据请求
            receipt_request = {
                "source": "API",
                "receipt_date": datetime.utcnow().isoformat() + "Z",
                "store_id": settings.loyverse_store_id,
                "line_items": self._prepare_line_items_with_taxes(receipt_data.get("line_items", []), tax_id),
                "payments": receipt_data.get("payments", []),
                "note": receipt_data.get("receipt_note", "")
            }
            
            # 如果有客户ID，添加客户信息
            if receipt_data.get("customer_id"):
                receipt_request["customer_id"] = receipt_data["customer_id"]
            
            # 验证必要字段
            if not receipt_request["line_items"]:
                raise ValueError("No line items provided")
            
            if not receipt_request["payments"]:
                raise ValueError("No payments provided")
            
            logger.info(f"Creating receipt with taxes for user {user_id}")
            logger.debug(f"Receipt request: {json.dumps(receipt_request, indent=2)}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/receipts",
                    headers=self.headers,
                    json=receipt_request
                ) as response:
                    
                    if response.status == 201:
                        receipt = await response.json()
                        
                        business_logger.log_pos_transaction(
                            user_id=user_id,
                            receipt_id=receipt.get("receipt_number"),
                            total_amount=sum(p.get("money_amount", 0) for p in receipt_request["payments"]),
                            transaction_type="sale"
                        )
                        
                        logger.info(f"Successfully created receipt {receipt.get('receipt_number')} for user {user_id}")
                        return receipt
                    
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to create receipt: {response.status} - {error_text}")
                        
                        business_logger.log_error(
                            user_id=user_id,
                            stage="pos",
                            error_code="RECEIPT_CREATION_FAILED",
                            error_msg=f"HTTP {response.status}: {error_text}"
                        )
                        
                        return {
                            "success": False,
                            "error": "RECEIPT_CREATION_FAILED",
                            "message": f"Error creating receipt: {response.status}"
                        }
                        
        except Exception as e:
            logger.error(f"Exception creating receipt: {e}")
            business_logger.log_error(
                user_id=user_id,
                stage="pos",
                error_code="RECEIPT_CREATION_EXCEPTION",
                error_msg=str(e),
                exception=e
            )
            
            return {
                "success": False,
                "error": "RECEIPT_CREATION_EXCEPTION",
                "message": str(e)
            }
    
    def _prepare_line_items_with_taxes(self, line_items: List[Dict[str, Any]], tax_id: Optional[str]) -> List[Dict[str, Any]]:
        """
        为每个line item添加税费信息
        根据Loyverse API，税费应该在每个line_item中指定
        """
        processed_items = []
        
        for item in line_items:
            line_item = {
                "quantity": item.get("quantity", 1),
                "variant_id": item.get("variant_id"),
                "price": item.get("price", 0)
            }
            
            # 添加税费信息到每个line item
            if tax_id:
                line_item["line_taxes"] = [{"id": tax_id}]
            
            # 添加备注
            if item.get("line_note"):
                line_item["line_note"] = item["line_note"]
            
            processed_items.append(line_item)
        
        return processed_items
    
    async def _get_ivu_tax_id(self, user_id: str) -> Optional[str]:
        """
        获取IVU税费的ID
        在Loyverse中，税费必须预先配置，然后通过ID引用
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/taxes",
                    headers=self.headers
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        taxes = data.get("taxes", [])
                        
                        # 查找IVU税费（按名称匹配）
                        for tax in taxes:
                            tax_name = tax.get("name", "").lower()
                            if "ivu" in tax_name or "impuesto" in tax_name:
                                return tax.get("id")
                        
                        # 如果没找到，返回第一个税费（假设已配置）
                        if taxes:
                            logger.warning(f"No IVU tax found, using first available tax: {taxes[0].get('name')}")
                            return taxes[0].get("id")
                        
                        logger.error("No taxes configured in Loyverse")
                        return None
                    
                    else:
                        logger.error(f"Failed to get taxes: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Exception getting tax ID: {e}")
            return None
    
    async def find_customer_by_phone(self, phone: str, user_id: str) -> Optional[Dict[str, Any]]:
        """根据电话号码查找客户"""
        try:
            # 清理电话号码格式
            clean_phone = self._clean_phone_number(phone)
            
            async with aiohttp.ClientSession() as session:
                # 使用电话号码搜索客户
                params = {
                    "phone_number": clean_phone,
                    "limit": 1
                }
                
                async with session.get(
                    f"{self.base_url}/customers",
                    headers=self.headers,
                    params=params
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        customers = data.get("customers", [])
                        
                        if customers:
                            logger.info(f"Found existing customer for phone {clean_phone}")
                            return customers[0]
                        else:
                            logger.info(f"No existing customer found for phone {clean_phone}")
                            return None
                    
                    else:
                        error_text = await response.text()
                        logger.warning(f"Error searching customer: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Exception finding customer by phone: {e}")
            return None
    
    async def create_customer(self, name: str, phone: str, user_id: str) -> Optional[str]:
        """创建新客户"""
        try:
            clean_phone = self._clean_phone_number(phone)
            
            customer_data = {
                "name": name,
                "phone_number": clean_phone,
                "email": None  # 可选
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/customers",
                    headers=self.headers,
                    json=customer_data
                ) as response:
                    
                    if response.status == 201:
                        customer = await response.json()
                        customer_id = customer.get("id")
                        
                        logger.info(f"Created new customer {customer_id} for {name} ({clean_phone})")
                        
                        business_logger.log_customer_activity(
                            user_id=user_id,
                            customer_id=customer_id,
                            activity_type="created",
                            details={"name": name, "phone": clean_phone}
                        )
                        
                        return customer_id
                    
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to create customer: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Exception creating customer: {e}")
            return None
    
    async def update_customer(self, customer_id: str, update_data: Dict[str, Any], user_id: str) -> bool:
        """更新客户信息"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{self.base_url}/customers/{customer_id}",
                    headers=self.headers,
                    json=update_data
                ) as response:
                    
                    if response.status == 200:
                        logger.info(f"Updated customer {customer_id}")
                        
                        business_logger.log_customer_activity(
                            user_id=user_id,
                            customer_id=customer_id,
                            activity_type="updated",
                            details=update_data
                        )
                        
                        return True
                    
                    else:
                        error_text = await response.text()
                        logger.warning(f"Failed to update customer: {response.status} - {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"Exception updating customer: {e}")
            return False
    
    async def get_menu_items(self, user_id: str) -> List[Dict[str, Any]]:
        """获取菜单项目"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/items",
                    headers=self.headers,
                    params={"limit": 250}  # 调整为适当的限制
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        items = data.get("items", [])
                        
                        logger.info(f"Retrieved {len(items)} menu items")
                        return items
                    
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get menu items: {response.status} - {error_text}")
                        return []
                        
        except Exception as e:
            logger.error(f"Exception getting menu items: {e}")
            return []
    
    async def get_categories(self, user_id: str) -> List[Dict[str, Any]]:
        """获取商品分类"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/categories",
                    headers=self.headers
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        categories = data.get("categories", [])
                        
                        logger.info(f"Retrieved {len(categories)} categories")
                        return categories
                    
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get categories: {response.status} - {error_text}")
                        return []
                        
        except Exception as e:
            logger.error(f"Exception getting categories: {e}")
            return []
    
    def _generate_receipt_number(self) -> str:
        """生成收据号码"""
        import uuid
        return f"API-{int(datetime.utcnow().timestamp())}-{str(uuid.uuid4())[:8]}"
    
    def _clean_phone_number(self, phone: str) -> str:
        """清理电话号码格式"""
        # 移除非数字字符
        import re
        clean = re.sub(r'[^\d+]', '', phone)
        
        # 确保有国际代码
        if not clean.startswith('+'):
            if clean.startswith('1'):
                clean = '+' + clean
            else:
                clean = '+1' + clean
        
        return clean
    
    async def test_connection(self, user_id: str) -> bool:
        """测试Loyverse API连接"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/stores",
                    headers=self.headers
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        stores = data.get("stores", [])
                        logger.info(f"Connection test successful. Found {len(stores)} stores")
                        return True
                    else:
                        logger.error(f"Connection test failed: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"Connection test exception: {e}")
            return False

# 全局Loyverse客户端实例
loyverse_client = LoyverseClient()
