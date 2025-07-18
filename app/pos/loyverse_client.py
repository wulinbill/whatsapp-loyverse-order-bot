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
        self.refresh_token = settings.loyverse_refresh_token
        self.base_url = "https://api.loyverse.com/v1.0"
        self.access_token = None
        self.token_expires_at = None
        self.cached_payment_types = None  # 缓存支付类型
    
    async def _get_access_token(self) -> str:
        """获取或刷新访问令牌"""
        if self.access_token and self.token_expires_at:
            # 检查令牌是否还有效（提前5分钟刷新）
            import time
            if time.time() < (self.token_expires_at - 300):
                return self.access_token
        
        # 刷新访问令牌
        await self._refresh_access_token()
        return self.access_token
    
    async def _refresh_access_token(self):
        """使用 refresh token 获取新的 access token"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": settings.loyverse_client_id,
                    "client_secret": settings.loyverse_client_secret
                }
                
                async with session.post(
                    "https://api.loyverse.com/oauth/token",
                    data=data
                ) as response:
                    
                    if response.status == 200:
                        token_data = await response.json()
                        self.access_token = token_data["access_token"]
                        
                        # 计算令牌过期时间
                        import time
                        expires_in = token_data.get("expires_in", 3600)
                        self.token_expires_at = time.time() + expires_in
                        
                        logger.info("Successfully refreshed Loyverse access token")
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to refresh token: {response.status} - {error_text}")
                        raise Exception(f"Token refresh failed: {response.status}")
                        
        except Exception as e:
            logger.error(f"Exception refreshing token: {e}")
            raise
    
    async def _get_headers(self) -> Dict[str, str]:
        """获取包含认证信息的请求头"""
        access_token = await self._get_access_token()
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    
    async def _get_cash_payment_type_id(self, user_id: str) -> Optional[str]:
        """
        获取现金支付类型的ID
        """
        try:
            # 如果已缓存，直接返回
            if self.cached_payment_types:
                for payment_type in self.cached_payment_types:
                    payment_name = payment_type.get("name", "").lower()
                    payment_type_value = payment_type.get("type", "").lower()
                    if "cash" in payment_name or "efectivo" in payment_name or payment_type_value == "cash":
                        return payment_type.get("id")
            
            headers = await self._get_headers()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/payment_types",
                    headers=headers
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        payment_types = data.get("payment_types", [])
                        self.cached_payment_types = payment_types
                        
                        # 查找现金支付类型
                        for payment_type in payment_types:
                            payment_name = payment_type.get("name", "").lower()
                            payment_type_value = payment_type.get("type", "").lower()
                            
                            # 匹配现金相关的名称或类型
                            if any(keyword in payment_name for keyword in ["cash", "efectivo", "dinero"]) or payment_type_value == "cash":
                                logger.info(f"Found cash payment type: {payment_type.get('name')} (ID: {payment_type.get('id')})")
                                return payment_type.get("id")
                        
                        # 如果没找到现金，使用第一个支付类型
                        if payment_types:
                            default_payment = payment_types[0]
                            logger.warning(f"No cash payment type found, using first available: {default_payment.get('name')} (ID: {default_payment.get('id')})")
                            return default_payment.get("id")
                        
                        logger.error("No payment types configured in Loyverse")
                        return None
                    
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get payment types: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Exception getting payment type ID: {e}")
            return None
    
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
            
            # 获取现金支付类型ID
            cash_payment_type_id = await self._get_cash_payment_type_id(user_id)
            if not cash_payment_type_id:
                return {
                    "success": False,
                    "error": "NO_PAYMENT_TYPE",
                    "message": "No se pudo obtener el tipo de pago. Verifique la configuración de Loyverse."
                }
            
            # 处理支付信息
            payments = receipt_data.get("payments", [])
            if payments:
                # 确保每个支付都有payment_type_id
                for payment in payments:
                    if not payment.get("payment_type_id"):
                        payment["payment_type_id"] = cash_payment_type_id
            else:
                # 如果没有提供支付信息，创建默认现金支付
                total_amount = sum(
                    item.get("price", 0) * item.get("quantity", 1) 
                    for item in receipt_data.get("line_items", [])
                )
                # 计算含税总额
                total_with_tax = total_amount * (1 + settings.tax_rate)
                
                payments = [{
                    "payment_type_id": cash_payment_type_id,
                    "money_amount": round(total_with_tax, 2)
                }]
            
            # 构建完整的收据请求
            receipt_request = {
                "source": "API",
                "receipt_date": datetime.utcnow().isoformat() + "Z",
                "store_id": settings.loyverse_store_id,
                "line_items": self._prepare_line_items_with_taxes(receipt_data.get("line_items", []), tax_id),
                "payments": payments,
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
            
            # 验证每个支付都有payment_type_id
            for payment in receipt_request["payments"]:
                if not payment.get("payment_type_id"):
                    raise ValueError("Missing payment_type_id in payment")
            
            logger.info(f"Creating receipt with taxes for user {user_id}")
            logger.debug(f"Receipt request: {json.dumps(receipt_request, indent=2)}")
            
            headers = await self._get_headers()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/receipts",
                    headers=headers,
                    json=receipt_request
                ) as response:
                    
                    if response.status == 200:  # Loyverse创建收据可能返回200而不是201
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
            headers = await self._get_headers()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/taxes",
                    headers=headers
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
            
            headers = await self._get_headers()
            
            async with aiohttp.ClientSession() as session:
                # 使用电话号码搜索客户
                # 注意：Loyverse API 可能不支持直接按phone_number搜索，需要获取所有客户然后过滤
                async with session.get(
                    f"{self.base_url}/customers",
                    headers=headers,
                    params={"limit": 250}  # 获取更多客户进行搜索
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        customers = data.get("customers", [])
                        
                        # 在客户列表中查找匹配的电话号码
                        for customer in customers:
                            customer_phone = customer.get("phone_number", "")
                            if customer_phone == clean_phone:
                                logger.info(f"Found existing customer for phone {clean_phone}")
                                return customer
                        
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
            
            headers = await self._get_headers()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/customers",
                    headers=headers,
                    json=customer_data
                ) as response:
                    
                    if response.status == 200:  # Loyverse可能返回200而不是201
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
            headers = await self._get_headers()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(  # Loyverse可能使用POST而不是PUT来更新
                    f"{self.base_url}/customers",
                    headers=headers,
                    json={**update_data, "id": customer_id}  # 包含ID来更新现有客户
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
            headers = await self._get_headers()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/items",
                    headers=headers,
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
            headers = await self._get_headers()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/categories",
                    headers=headers
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
            headers = await self._get_headers()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/stores",
                    headers=headers
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
