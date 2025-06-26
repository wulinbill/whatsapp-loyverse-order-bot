import time
from typing import Dict, List, Any, Optional, Tuple
import json
import re

from ..config import get_settings
from ..logger import get_logger, business_logger
from .loyverse_client import loyverse_client
from ..utils.alias_matcher import alias_matcher

settings = get_settings()
logger = get_logger(__name__)

class OrderProcessor:
    """订单处理器，负责将用户订单转换为POS系统格式"""
    
    def __init__(self):
        self.tax_rate = settings.tax_rate  # 11.5% IVU
        self.store_id = settings.loyverse_store_id
    
    async def place_order(self, customer_name: str, customer_phone: str, matched_items: List[Dict[str, Any]], user_id: str) -> Dict[str, Any]:
        """
        完整的订单处理流程 - 按照文档步骤6到7
        
        Args:
            customer_name: 客户姓名
            customer_phone: 客户电话号码
            matched_items: 匹配的菜品项目
            user_id: 用户ID
            
        Returns:
            处理结果
        """
        try:
            logger.info(f"Processing order for customer {customer_name} ({customer_phone})")
            
            # 1. 应用Kong Food的订餐规则
            processed_items = self._apply_ordering_rules(matched_items)
            
            # 2. 转换为Loyverse格式
            line_items = self._convert_to_loyverse_format(processed_items)
            
            # 3. 计算总价（包含税费）
            total_info = self._calculate_totals_with_tax(line_items)
            
            # 4. 处理客户信息
            customer_id = await self._handle_customer(customer_name, customer_phone, user_id)
            
            # 5. 确定准备时间
            preparation_time = self._calculate_preparation_time(processed_items)
            
            # 6. 创建Loyverse收据（使用正确的税费处理）
            receipt_data = {
                "customer_id": customer_id,
                "line_items": line_items,
                "payments": [{
                    "payment_type_id": None,  # 如果有现金支付类型ID，在这里设置
                    "money_amount": total_info["total_with_tax"]
                }],
                "receipt_note": f"Cliente: {customer_name}\nTeléfono: {customer_phone}\nTiempo estimado: {preparation_time} min"
            }
            
            receipt = await loyverse_client.create_receipt_with_taxes(receipt_data, user_id)
            
            return {
                "success": True,
                "receipt": receipt,
                "line_items": processed_items,
                "total_with_tax": total_info["total_with_tax"],
                "subtotal": total_info["subtotal"],
                "tax_amount": total_info["tax_amount"],
                "preparation_time": preparation_time,
                "customer_id": customer_id,
                "customer_name": customer_name,
                "customer_phone": customer_phone
            }
            
        except Exception as e:
            business_logger.log_error(
                user_id=user_id,
                stage="pos",
                error_code="ORDER_PROCESSING_FAILED",
                error_msg=str(e),
                exception=e
            )
            return {
                "success": False,
                "error": "PROCESSING_ERROR",
                "message": "Error al procesar el pedido. Inténtelo de nuevo."
            }
    
    def _apply_ordering_rules(self, matched_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """应用Kong Food的订餐规则"""
        processed_items = []
        
        for item in matched_items:
            if item.get("needs_choice", False):
                # 跳过仍需选择的项目
                continue
                
            processed_item = item.copy()
            
            # 应用Combinaciones规则
            if self._is_combinaciones(item):
                additional_items = self._apply_combinaciones_rules(item)
                processed_items.extend(additional_items)
            
            # 应用Pollo Frito规则
            elif self._is_pollo_frito(item):
                additional_items = self._apply_pollo_frito_rules(item)
                processed_items.extend(additional_items)
            
            # 处理修饰符
            modifier_items = self._process_modifiers(item)
            processed_items.extend(modifier_items)
            
            processed_items.append(processed_item)
        
        return processed_items
    
    def _is_combinaciones(self, item: Dict[str, Any]) -> bool:
        """判断是否为Combinaciones类别"""
        category = item.get("category_name", "").lower()
        return "combinaciones" in category
    
    def _is_pollo_frito(self, item: Dict[str, Any]) -> bool:
        """判断是否为Pollo Frito类别"""
        category = item.get("category_name", "").lower()
        item_name = item.get("item_name", "").lower()
        return "pollo frito" in category or "presas de pollo" in item_name
    
    def _apply_combinaciones_rules(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """应用Combinaciones规则"""
        additional_items = []
        modifiers = item.get("modifiers", [])
        
        # 检查是否有换搭配的要求
        for modifier in modifiers:
            modifier_lower = modifier.lower()
            
            # 处理换搭配
            if any(word in modifier_lower for word in ["cambio", "con tostones", "换成"]):
                if "tostones" in modifier_lower:
                    # 添加换成tostones的项目
                    change_item = self._find_cambio_item("arroz+tostones")
                    if change_item:
                        additional_items.append(change_item)
                elif "pana" in modifier_lower:
                    # 添加换成pana的项目
                    change_item = self._find_cambio_item("arroz+pana")
                    if change_item:
                        additional_items.append(change_item)
        
        return additional_items
    
    def _apply_pollo_frito_rules(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """应用Pollo Frito规则"""
        additional_items = []
        modifiers = item.get("modifiers", [])
        quantity = item.get("quantity", 1)
        
        # 提取鸡肉部位要求
        cadera_count = 0
        muro_count = 0
        pechuga_count = 0
        
        for modifier in modifiers:
            modifier_lower = modifier.lower()
            
            # 提取数量和部位
            cadera_match = re.search(r'(\d+)\s*cadera', modifier_lower)
            if cadera_match:
                cadera_count = int(cadera_match.group(1))
            
            muro_match = re.search(r'(\d+)\s*muro', modifier_lower)
            if muro_match:
                muro_count = int(muro_match.group(1))
            
            pechuga_match = re.search(r'(\d+)\s*pechuga', modifier_lower)
            if pechuga_match:
                pechuga_count = int(pechuga_match.group(1))
        
        # 如果指定了部位，添加对应的adicionales项目
        if cadera_count > 0:
            cadera_item = self._find_adicionales_item("cadera")
            if cadera_item:
                cadera_item["quantity"] = cadera_count
                additional_items.append(cadera_item)
        
        if muro_count > 0:
            muro_item = self._find_adicionales_item("muro")
            if muro_item:
                muro_item["quantity"] = muro_count
                additional_items.append(muro_item)
        
        if pechuga_count > 0:
            pechuga_item = self._find_adicionales_item("pechuga")
            if pechuga_item:
                pechuga_item["quantity"] = pechuga_count
                additional_items.append(pechuga_item)
        
        return additional_items
    
    def _process_modifiers(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """处理修饰符，转换为adicionales项目"""
        modifier_items = []
        modifiers = item.get("modifiers", [])
        
        for modifier in modifiers:
            modifier_lower = modifier.lower()
            
            # 处理extra项目
            if modifier_lower.startswith("extra"):
                ingredient = modifier_lower.replace("extra", "").strip()
                extra_item = self._find_adicionales_item(f"extra {ingredient}")
                if extra_item:
                    modifier_items.append(extra_item)
            
            # 处理poco项目
            elif modifier_lower.startswith("poco"):
                ingredient = modifier_lower.replace("poco", "").strip()
                poco_item = self._find_adicionales_item(f"poco {ingredient}")
                if poco_item:
                    modifier_items.append(poco_item)
            
            # 处理no/sin项目
            elif any(word in modifier_lower for word in ["no ", "sin "]):
                for neg_word in ["no ", "sin "]:
                    if neg_word in modifier_lower:
                        ingredient = modifier_lower.replace(neg_word, "").strip()
                        no_item = self._find_adicionales_item(f"no {ingredient}")
                        if no_item:
                            modifier_items.append(no_item)
                        break
            
            # 处理aparte项目
            elif "aparte" in modifier_lower:
                ingredient = modifier_lower.replace("aparte", "").strip()
                aparte_item = self._find_adicionales_item(f"{ingredient} aparte")
                if aparte_item:
                    modifier_items.append(aparte_item)
            
            # 处理salsa项目
            elif "salsa" in modifier_lower:
                salsa_type = modifier_lower.replace("salsa", "").strip()
                if salsa_type:
                    salsa_item = self._find_adicionales_item(f"salsa {salsa_type}")
                    if salsa_item:
                        modifier_items.append(salsa_item)
        
        return modifier_items
    
    def _find_cambio_item(self, cambio_type: str) -> Optional[Dict[str, Any]]:
        """查找cambio类型的adicionales项目"""
        return self._find_adicionales_item_by_variant(cambio_type)
    
    def _find_adicionales_item(self, search_term: str) -> Optional[Dict[str, Any]]:
        """查找adicionales类别的项目"""
        matches = alias_matcher.find_matches(search_term, "system", limit=1)
        
        for match in matches:
            if match.get("category_name") == "Adicionales":
                return {
                    "item_id": match.get("item_id"),
                    "variant_id": match.get("variant_id"),
                    "item_name": match.get("item_name"),
                    "category_name": match.get("category_name"),
                    "price": match.get("price", 0),
                    "sku": match.get("sku"),
                    "quantity": 1
                }
        
        return None
    
    def _find_adicionales_item_by_variant(self, variant_name: str) -> Optional[Dict[str, Any]]:
        """根据variant名称查找adicionales项目"""
        # 这里需要更精确的匹配逻辑，可能需要直接查询菜单数据
        # 暂时使用简化版本
        return self._find_adicionales_item(variant_name)
    
    def _convert_to_loyverse_format(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """转换为Loyverse API格式"""
        line_items = []
        
        for item in items:
            line_item = {
                "quantity": item.get("quantity", 1),
                "variant_id": item.get("variant_id"),
                "price": item.get("price", 0)
            }
            
            # 添加备注（组合修饰符信息）
            modifiers = item.get("modifiers", [])
            if modifiers:
                line_item["line_note"] = "; ".join(modifiers)
            
            line_items.append(line_item)
        
        return line_items
    
    def _calculate_totals_with_tax(self, line_items: List[Dict[str, Any]]) -> Dict[str, float]:
        """计算订单总价，包含正确的税费计算"""
        subtotal = sum(item.get("price", 0) * item.get("quantity", 1) for item in line_items)
        tax_amount = subtotal * self.tax_rate
        total_with_tax = subtotal + tax_amount
        
        return {
            "subtotal": round(subtotal, 2),
            "tax_amount": round(tax_amount, 2),
            "total_with_tax": round(total_with_tax, 2),
            "tax_rate": self.tax_rate
        }
    
    def _calculate_preparation_time(self, items: List[Dict[str, Any]]) -> int:
        """
        计算准备时间 - 按照文档规则
        < 3 platos principales → 10 min
        ≥ 3 platos principales → 15 min
        """
        main_dish_count = 0
        main_dish_categories = ["combinaciones", "pollo frito", "carnes", "mariscos"]
        
        for item in items:
            category = item.get("category_name", "").lower()
            if any(main_cat in category for main_cat in main_dish_categories):
                main_dish_count += item.get("quantity", 1)
        
        return 15 if main_dish_count >= 3 else 10
    
    async def _handle_customer(self, name: str, phone: str, user_id: str) -> Optional[str]:
        """处理客户信息 - 步骤5"""
        if not phone:
            return None
        
        # 查找现有客户
        existing_customer = await loyverse_client.find_customer_by_phone(phone, user_id)
        
        if existing_customer:
            # 更新客户姓名（如果需要）
            customer_id = existing_customer.get("id")
            current_name = existing_customer.get("name", "")
            
            if current_name != name and not current_name.startswith("Cliente"):
                # 只有当前名称是临时名称时才更新
                await loyverse_client.update_customer(customer_id, {"name": name}, user_id)
            
            return customer_id
        
        # 创建新客户
        customer_id = await loyverse_client.create_customer(
            name=name,
            phone=phone,
            user_id=user_id
        )
        
        return customer_id

# 全局订单处理器实例
order_processor = OrderProcessor()
