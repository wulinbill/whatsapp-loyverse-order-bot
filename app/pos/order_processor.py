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
        self.tax_rate = settings.tax_rate
        self.store_id = settings.loyverse_store_id
    
    async def process_order(self, order_data: Dict[str, Any], user_id: str, customer_phone: str) -> Dict[str, Any]:
        """
        处理完整的订单流程
        
        Args:
            order_data: Claude提取的订单数据
            user_id: 用户ID
            customer_phone: 客户电话号码
            
        Returns:
            处理结果
        """
        try:
            logger.info(f"Processing order for user {user_id}")
            
            # 1. 匹配菜单项
            matched_items = await self._match_menu_items(order_data.get("order_lines", []), user_id)
            
            if not matched_items:
                return {
                    "success": False,
                    "error": "NO_ITEMS_MATCHED",
                    "message": "No se pudieron encontrar los productos solicitados."
                }
            
            # 2. 应用Kong Food的订餐规则
            processed_items = self._apply_ordering_rules(matched_items)
            
            # 3. 转换为Loyverse格式
            line_items = self._convert_to_loyverse_format(processed_items)
            
            # 4. 计算总价
            total_info = self._calculate_totals(line_items)
            
            # 5. 处理客户信息
            customer_id = await self._handle_customer(customer_phone, user_id)
            
            # 6. 创建订单
            receipt = await loyverse_client.create_receipt(customer_id, line_items, user_id)
            
            return {
                "success": True,
                "receipt": receipt,
                "matched_items": processed_items,
                "total_info": total_info,
                "customer_id": customer_id
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
    
    async def _match_menu_items(self, order_lines: List[Dict[str, Any]], user_id: str) -> List[Dict[str, Any]]:
        """匹配菜单项"""
        matched_items = []
        
        for line in order_lines:
            alias = line.get("alias", "")
            quantity = line.get("quantity", 1)
            modifiers = line.get("modifiers", [])
            
            if not alias:
                continue
            
            # 使用别名匹配器查找菜品
            matches = alias_matcher.find_matches(alias, user_id, limit=5)
            
            if matches:
                # 选择最佳匹配
                best_match = matches[0]
                
                matched_item = {
                    "item_id": best_match.get("item_id"),
                    "variant_id": best_match.get("variant_id"),
                    "item_name": best_match.get("item_name"),
                    "category_name": best_match.get("category_name"),
                    "price": best_match.get("price", 0),
                    "sku": best_match.get("sku"),
                    "quantity": quantity,
                    "modifiers": modifiers,
                    "match_score": best_match.get("score", 0)
                }
                
                matched_items.append(matched_item)
            else:
                logger.warning(f"No match found for alias: {alias}")
        
        return matched_items
    
    def _apply_ordering_rules(self, matched_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """应用Kong Food的订餐规则"""
        processed_items = []
        
        for item in matched_items:
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
    
    def _calculate_totals(self, line_items: List[Dict[str, Any]]) -> Dict[str, float]:
        """计算订单总价"""
        subtotal = sum(item.get("price", 0) * item.get("quantity", 1) for item in line_items)
        tax_amount = subtotal * self.tax_rate
        total_with_tax = subtotal + tax_amount
        
        return {
            "subtotal": round(subtotal, 2),
            "tax_amount": round(tax_amount, 2),
            "total_with_tax": round(total_with_tax, 2),
            "tax_rate": self.tax_rate
        }
    
    async def _handle_customer(self, phone: str, user_id: str) -> Optional[str]:
        """处理客户信息"""
        if not phone:
            return None
        
        # 查找现有客户
        existing_customer = await loyverse_client.find_customer_by_phone(phone, user_id)
        
        if existing_customer:
            return existing_customer.get("id")
        
        # 创建新客户（如果需要姓名，可以在后续流程中更新）
        customer_id = await loyverse_client.create_customer(
            name=f"Cliente {phone[-4:]}",  # 临时名称
            phone=phone,
            user_id=user_id
        )
        
        return customer_id
    
    async def update_customer_name(self, customer_id: str, name: str, user_id: str) -> bool:
        """更新客户姓名"""
        # 这里可以添加更新客户信息的逻辑
        # 目前Loyverse API的customer更新需要具体实现
        logger.info(f"Would update customer {customer_id} name to {name}")
        return True

# 全局订单处理器实例
order_processor = OrderProcessor()
