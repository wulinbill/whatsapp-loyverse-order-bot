#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具函数模块
提供菜单搜索、订单处理等实用功能
100%使用本地菜单知识库，确保准确性
"""

import os
import json
import re
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from fuzzywuzzy import fuzz, process
import unicodedata
import loyverse_api

logger = logging.getLogger(__name__)

# 菜单数据路径
KB_PATH = os.path.join(os.path.dirname(__file__), "data", "menu_kb.json")

# 全局菜单数据缓存
_menu_data_cache = None
_cache_loaded_at = None

def load_menu_data(force_reload: bool = False) -> Dict[str, Any]:
    """
    从本地JSON文件加载菜单数据（带缓存和验证）
    
    Args:
        force_reload: 是否强制重新加载
        
    Returns:
        菜单数据字典
        
    Note:
        此函数100%使用本地菜单知识库，不访问任何API
        确保菜单数据的准确性和一致性
    """
    global _menu_data_cache, _cache_loaded_at
    
    # 如果缓存存在且不强制重载，返回缓存
    if _menu_data_cache is not None and not force_reload:
        logger.debug("📚 Using cached menu data")
        return _menu_data_cache
    
    try:
        # 验证文件存在
        if not os.path.exists(KB_PATH):
            raise FileNotFoundError(f"Menu knowledge base not found: {KB_PATH}")
        
        # 获取文件信息
        file_stat = os.stat(KB_PATH)
        file_size = file_stat.st_size
        file_modified = datetime.fromtimestamp(file_stat.st_mtime)
        
        logger.info(f"📖 Loading menu data from local file: {KB_PATH}")
        logger.info(f"📊 File size: {file_size:,} bytes, modified: {file_modified}")
        
        # 读取并解析JSON文件
        with open(KB_PATH, 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        # 验证菜单数据结构
        validation_result = validate_menu_structure(menu_data)
        if not validation_result["valid"]:
            logger.error(f"❌ Invalid menu structure: {validation_result['errors']}")
            raise ValueError(f"Invalid menu data structure: {validation_result['errors']}")
        
        # 缓存数据
        _menu_data_cache = menu_data
        _cache_loaded_at = datetime.now()
        
        # 记录加载统计
        stats = get_menu_loading_stats(menu_data)
        logger.info(f"✅ Menu data loaded successfully: {stats}")
        
        return _menu_data_cache
        
    except FileNotFoundError as e:
        logger.error(f"❌ Menu file not found: {e}")
        _menu_data_cache = create_empty_menu_structure()
        return _menu_data_cache
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in menu file: {e}")
        _menu_data_cache = create_empty_menu_structure()
        return _menu_data_cache
        
    except Exception as e:
        logger.error(f"❌ Failed to load menu data: {e}")
        _menu_data_cache = create_empty_menu_structure()
        return _menu_data_cache

def validate_menu_structure(menu_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证菜单数据结构的完整性
    
    Args:
        menu_data: 菜单数据字典
        
    Returns:
        验证结果字典
    """
    errors = []
    
    try:
        # 检查顶级结构
        if not isinstance(menu_data, dict):
            errors.append("Menu data must be a dictionary")
            return {"valid": False, "errors": errors}
        
        if "menu_categories" not in menu_data:
            errors.append("Missing 'menu_categories' key")
            return {"valid": False, "errors": errors}
        
        categories = menu_data["menu_categories"]
        if not isinstance(categories, dict):
            errors.append("'menu_categories' must be a dictionary")
            return {"valid": False, "errors": errors}
        
        # 验证每个分类
        total_items = 0
        valid_categories = 0
        
        for category_key, category in categories.items():
            if not isinstance(category, dict):
                errors.append(f"Category '{category_key}' must be a dictionary")
                continue
            
            # 检查分类必要字段
            required_fields = ["name", "items"]
            for field in required_fields:
                if field not in category:
                    errors.append(f"Category '{category_key}' missing field: {field}")
                    continue
            
            # 验证项目列表
            items = category.get("items", [])
            if not isinstance(items, list):
                errors.append(f"Category '{category_key}' items must be a list")
                continue
            
            # 验证每个项目
            for i, item in enumerate(items):
                item_errors = validate_menu_item(item, f"{category_key}[{i}]")
                errors.extend(item_errors)
            
            total_items += len(items)
            valid_categories += 1
        
        # 记录验证统计
        logger.debug(f"🔍 Validation: {valid_categories} categories, {total_items} items, {len(errors)} errors")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "stats": {
                "categories": valid_categories,
                "total_items": total_items,
                "error_count": len(errors)
            }
        }
        
    except Exception as e:
        return {
            "valid": False,
            "errors": [f"Validation error: {str(e)}"]
        }

def validate_menu_item(item: Dict[str, Any], context: str) -> list:
    """
    验证单个菜单项目的数据完整性
    
    Args:
        item: 菜单项目数据
        context: 上下文信息（用于错误报告）
        
    Returns:
        错误列表
    """
    errors = []
    
    try:
        # 检查必要字段
        required_fields = ["item_id", "item_name", "variant_id", "price"]
        for field in required_fields:
            if field not in item:
                errors.append(f"{context}: Missing required field '{field}'")
            elif not item[field] and field != "price":  # price可以为0
                errors.append(f"{context}: Empty value for required field '{field}'")
        
        # 验证数据类型
        if "price" in item:
            try:
                price = float(item["price"])
                if price < 0:
                    errors.append(f"{context}: Price cannot be negative: {price}")
            except (ValueError, TypeError):
                errors.append(f"{context}: Invalid price format: {item['price']}")
        
        # 验证可选字段
        optional_lists = ["aliases", "keywords"]
        for field in optional_lists:
            if field in item and not isinstance(item[field], list):
                errors.append(f"{context}: Field '{field}' must be a list")
        
        return errors
        
    except Exception as e:
        return [f"{context}: Validation error: {str(e)}"]

def get_menu_loading_stats(menu_data: Dict[str, Any]) -> str:
    """
    获取菜单加载统计信息
    
    Args:
        menu_data: 菜单数据
        
    Returns:
        统计信息字符串
    """
    try:
        categories = menu_data.get("menu_categories", {})
        total_categories = len(categories)
        total_items = 0
        
        for category in categories.values():
            if isinstance(category, dict):
                items = category.get("items", [])
                total_items += len(items)
        
        return f"{total_categories} categories, {total_items} menu items"
        
    except Exception:
        return "unknown statistics"

def create_empty_menu_structure() -> Dict[str, Any]:
    """
    创建空的菜单结构（作为fallback）
    
    Returns:
        空的菜单数据结构
    """
    return {
        "menu_categories": {},
        "restaurant_info": {
            "name": "Kong Food Restaurant",
            "status": "menu_loading_failed"
        }
    }

def normalize_text(text: str) -> str:
    """
    标准化文本用于搜索匹配
    
    Args:
        text: 原始文本
        
    Returns:
        标准化后的文本
    """
    if not text:
        return ""
    
    # Unicode标准化
    normalized = unicodedata.normalize('NFD', text)
    
    # 移除重音符号
    no_accents = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    
    # 转换为小写并移除多余空格
    cleaned = re.sub(r'[^\w\s]', '', no_accents.lower()).strip()
    
    # 移除多余的空格
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    return cleaned

def search_menu(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    搜索菜单项目
    支持模糊匹配、别名匹配、关键词匹配
    100%使用本地菜单知识库
    
    Args:
        query: 搜索查询
        limit: 返回结果数量限制
        
    Returns:
        匹配的菜单项目列表，按相似度排序
    """
    if not query or not query.strip():
        return []
    
    try:
        menu_data = load_menu_data()
        normalized_query = normalize_text(query)
        
        if not normalized_query:
            return []
        
        logger.debug(f"🔍 Searching for: '{query}' (normalized: '{normalized_query}')")
        
        # 收集所有菜单项目
        all_items = []
        for category in menu_data.get("menu_categories", {}).values():
            if isinstance(category, dict) and "items" in category:
                all_items.extend(category["items"])
        
        if not all_items:
            logger.warning("No menu items found in data")
            return []
        
        # 计算匹配分数
        scored_items = []
        
        for item in all_items:
            scores = calculate_item_scores(item, normalized_query)
            max_score = max(scores.values()) if scores else 0
            
            if max_score >= 60:  # 最低匹配阈值
                scored_items.append({
                    "item": item,
                    "score": max_score,
                    "match_type": get_best_match_type(scores)
                })
        
        # 按分数排序
        scored_items.sort(key=lambda x: x["score"], reverse=True)
        
        # 返回top结果
        results = [scored_item["item"] for scored_item in scored_items[:limit]]
        
        logger.debug(f"✅ Found {len(results)} matches for '{query}'")
        
        return results
        
    except Exception as e:
        logger.error(f"Error searching menu for '{query}': {e}")
        return []

def calculate_item_scores(item: Dict[str, Any], normalized_query: str) -> Dict[str, float]:
    """
    计算菜单项目的各种匹配分数
    
    Args:
        item: 菜单项目
        normalized_query: 标准化的查询字符串
        
    Returns:
        包含各种匹配类型分数的字典
    """
    scores = {}
    
    # 主名称匹配
    item_name = normalize_text(item.get("item_name", ""))
    if item_name:
        scores["name_exact"] = 100 if normalized_query == item_name else 0
        scores["name_partial"] = fuzz.partial_ratio(normalized_query, item_name)
        scores["name_ratio"] = fuzz.ratio(normalized_query, item_name)
    
    # 别名匹配
    aliases = item.get("aliases", [])
    if aliases:
        alias_scores = []
        for alias in aliases:
            normalized_alias = normalize_text(alias)
            if normalized_alias:
                alias_scores.extend([
                    100 if normalized_query == normalized_alias else 0,
                    fuzz.partial_ratio(normalized_query, normalized_alias),
                    fuzz.ratio(normalized_query, normalized_alias)
                ])
        if alias_scores:
            scores["alias_best"] = max(alias_scores)
    
    # 关键词匹配
    keywords = item.get("keywords", [])
    if keywords:
        keyword_scores = []
        for keyword in keywords:
            normalized_keyword = normalize_text(keyword)
            if normalized_keyword:
                keyword_scores.extend([
                    100 if normalized_query == normalized_keyword else 0,
                    fuzz.partial_ratio(normalized_query, normalized_keyword),
                    fuzz.ratio(normalized_query, normalized_keyword)
                ])
        if keyword_scores:
            scores["keyword_best"] = max(keyword_scores)
    
    # SKU匹配（精确匹配）
    sku = item.get("sku", "")
    if sku and normalized_query == normalize_text(sku):
        scores["sku_exact"] = 100
    
    return scores

def get_best_match_type(scores: Dict[str, float]) -> str:
    """
    获取最佳匹配类型
    
    Args:
        scores: 分数字典
        
    Returns:
        最佳匹配类型
    """
    if not scores:
        return "none"
    
    max_score = max(scores.values())
    
    for score_type, score in scores.items():
        if score == max_score:
            return score_type
    
    return "unknown"

def get_menu_by_category(category_name: str) -> List[Dict[str, Any]]:
    """
    获取指定分类的菜单项目
    
    Args:
        category_name: 分类名称
        
    Returns:
        该分类的菜单项目列表
    """
    try:
        menu_data = load_menu_data()
        
        for category in menu_data.get("menu_categories", {}).values():
            if isinstance(category, dict):
                if category.get("name", "").lower() == category_name.lower():
                    return category.get("items", [])
        
        logger.warning(f"Category not found: {category_name}")
        return []
        
    except Exception as e:
        logger.error(f"Error getting category '{category_name}': {e}")
        return []

def get_menu_item_by_id(item_id: str) -> Optional[Dict[str, Any]]:
    """
    根据ID获取菜单项目
    
    Args:
        item_id: 项目ID
        
    Returns:
        菜单项目字典，如果未找到返回None
    """
    try:
        menu_data = load_menu_data()
        
        for category in menu_data.get("menu_categories", {}).values():
            if isinstance(category, dict) and "items" in category:
                for item in category["items"]:
                    if item.get("item_id") == item_id:
                        return item
        
        logger.warning(f"Menu item not found: {item_id}")
        return None
        
    except Exception as e:
        logger.error(f"Error getting item by ID '{item_id}': {e}")
        return None

def get_menu_item_by_variant_id(variant_id: str) -> Optional[Dict[str, Any]]:
    """
    根据variant_id获取菜单项目
    
    Args:
        variant_id: 变体ID
        
    Returns:
        菜单项目字典，如果未找到返回None
    """
    try:
        menu_data = load_menu_data()
        
        for category in menu_data.get("menu_categories", {}).values():
            if isinstance(category, dict) and "items" in category:
                for item in category["items"]:
                    if item.get("variant_id") == variant_id:
                        return item
        
        logger.warning(f"Menu item not found by variant_id: {variant_id}")
        return None
        
    except Exception as e:
        logger.error(f"Error getting item by variant_id '{variant_id}': {e}")
        return None

def format_menu_item(item: Dict[str, Any], include_details: bool = False) -> str:
    """
    格式化菜单项目为显示字符串
    
    Args:
        item: 菜单项目
        include_details: 是否包含详细信息
        
    Returns:
        格式化的字符串
    """
    try:
        name = item.get("item_name", "Unknown Item")
        price = item.get("price", 0.0)
        
        formatted = f"{name} - ${price:.2f}"
        
        if include_details:
            category = item.get("category_name", "")
            if category:
                formatted += f" ({category})"
            
            aliases = item.get("aliases", [])
            if aliases:
                formatted += f" [别名: {', '.join(aliases[:2])}]"
        
        return formatted
        
    except Exception as e:
        logger.error(f"Error formatting menu item: {e}")
        return "Error formatting item"

def get_popular_items(limit: int = 5) -> List[Dict[str, Any]]:
    """
    获取热门菜品（基于简单规则）
    
    Args:
        limit: 返回数量限制
        
    Returns:
        热门菜品列表
    """
    try:
        # 简单实现：返回价格适中的Combinaciones
        combo_items = get_menu_by_category("Combinaciones")
        
        # 按价格排序，选择中等价位的作为热门
        combo_items.sort(key=lambda x: x.get("price", 0))
        
        # 选择中间价位的项目
        start_idx = len(combo_items) // 4
        end_idx = start_idx + limit
        
        popular = combo_items[start_idx:end_idx]
        
        logger.debug(f"🔥 Retrieved {len(popular)} popular items")
        return popular
        
    except Exception as e:
        logger.error(f"Error getting popular items: {e}")
        return []

def place_loyverse_order(items: List[Dict[str, Any]]) -> str:
    """
    向Loyverse POS系统下单 (修正版)
    
    Args:
        items: 订单项目列表
        
    Returns:
        收据编号
        
    Raises:
        Exception: 当下单失败时
    """
    try:
        if not items:
            raise ValueError("Cannot place empty order")
        
        # 验证订单项目
        for item in items:
            required_fields = ["variant_id", "quantity", "price"]
            for field in required_fields:
                if field not in item:
                    raise ValueError(f"Missing required field '{field}' in order item")
        
        # 获取POS设备ID (修正: 使用正确的环境变量名)
        pos_device_id = os.getenv("LOYVERSE_POS_DEVICE_ID")
        if not pos_device_id:
            raise ValueError("LOYVERSE_POS_DEVICE_ID not configured")
        
        # 获取商店ID
        store_id = os.getenv("LOYVERSE_STORE_ID")
        if not store_id:
            raise ValueError("LOYVERSE_STORE_ID not configured")
        
        # 计算总金额
        total_amount = sum(float(item["price"]) * int(item["quantity"]) for item in items)
        
        # 构建订单负载 (使用正确的Loyverse API结构)
        payload = {
            "store_id": store_id,
            "pos_device_id": pos_device_id,  # 修正字段名
            "line_items": [
                {
                    "variant_id": item["variant_id"],
                    "quantity": int(item["quantity"]),
                    "price": float(item["price"])  # 保持小数格式
                }
                for item in items
            ],
            "payments": [
                {
                    # 使用默认现金支付
                    "payment_type_id": get_default_payment_type_id(),
                    "money_amount": total_amount,
                    "name": "Cash",
                    "type": "CASH"
                }
            ]
        }
        
        logger.info(f"📤 Placing order with {len(items)} items, total: ${total_amount:.2f}")
        
        # 调用Loyverse API
        response = loyverse_api.place_order(payload)
        
        receipt_number = response.get("receipt_number", "unknown")
        
        logger.info(f"✅ Order placed successfully: Receipt #{receipt_number}")
        
        return receipt_number
        
    except Exception as e:
        logger.error(f"Failed to place Loyverse order: {e}")
        raise Exception(f"Failed to place order: {str(e)}")

def get_default_payment_type_id() -> str:
    """
    获取默认支付方式ID
    
    Returns:
        默认支付方式ID
    """
    # 可以从环境变量配置，或从API获取
    default_payment_id = os.getenv("LOYVERSE_DEFAULT_PAYMENT_TYPE_ID")
    if default_payment_id:
        return default_payment_id
    
    # 使用通用的现金支付类型
    # 注意: 实际使用时需要从Loyverse获取正确的payment_type_id
    return "cash"  # 这需要根据实际POS系统配置

def validate_order_items(items: List[Dict[str, Any]]) -> bool:
    """
    验证订单项目格式
    
    Args:
        items: 订单项目列表
        
    Returns:
        是否所有项目都有效
    """
    try:
        if not items:
            return False
        
        required_fields = ["variant_id", "quantity", "price"]
        
        for item in items:
            # 检查必要字段
            for field in required_fields:
                if field not in item:
                    logger.error(f"Missing field '{field}' in order item")
                    return False
            
            # 验证数据类型
            try:
                quantity = int(item["quantity"])
                price = float(item["price"])
                
                if quantity <= 0:
                    logger.error(f"Invalid quantity: {quantity}")
                    return False
                
                if price < 0:
                    logger.error(f"Invalid price: {price}")
                    return False
                    
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid data type in order item: {e}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error validating order items: {e}")
        return False

def get_menu_statistics() -> Dict[str, Any]:
    """
    获取菜单统计信息
    
    Returns:
        统计信息字典
    """
    try:
        menu_data = load_menu_data()
        stats = {
            "total_categories": 0,
            "total_items": 0,
            "price_range": {"min": float("inf"), "max": 0},
            "categories": {}
        }
        
        for category_name, category in menu_data.get("menu_categories", {}).items():
            if isinstance(category, dict) and "items" in category:
                items = category["items"]
                item_count = len(items)
                
                stats["total_categories"] += 1
                stats["total_items"] += item_count
                stats["categories"][category_name] = item_count
                
                # 计算价格范围
                for item in items:
                    price = item.get("price", 0)
                    if price > 0:
                        stats["price_range"]["min"] = min(stats["price_range"]["min"], price)
                        stats["price_range"]["max"] = max(stats["price_range"]["max"], price)
        
        # 处理空菜单的情况
        if stats["price_range"]["min"] == float("inf"):
            stats["price_range"]["min"] = 0
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting menu statistics: {e}")
        return {"error": str(e)}

def search_menu_by_keywords(keywords: List[str], limit: int = 5) -> List[Dict[str, Any]]:
    """
    根据关键词列表搜索菜单
    
    Args:
        keywords: 关键词列表
        limit: 返回结果数量限制
        
    Returns:
        匹配的菜单项目列表
    """
    try:
        if not keywords:
            return []
        
        # 合并关键词为搜索查询
        query = " ".join(keywords)
        return search_menu(query, limit)
        
    except Exception as e:
        logger.error(f"Error searching menu by keywords {keywords}: {e}")
        return []

def get_item_suggestions(query: str, limit: int = 3) -> List[str]:
    """
    获取物品建议
    
    Args:
        query: 搜索查询
        limit: 建议数量限制
        
    Returns:
        建议物品名称列表
    """
    try:
        # 使用较低的匹配阈值获取更多候选项
        candidates = search_menu(query, limit=limit * 2)
        
        suggestions = []
        for item in candidates[:limit]:
            suggestions.append(item["item_name"])
        
        return suggestions
        
    except Exception as e:
        logger.error(f"Error getting suggestions for '{query}': {e}")
        return []

def format_menu_category(category_name: str, include_prices: bool = True) -> str:
    """
    格式化菜单分类为显示字符串
    
    Args:
        category_name: 分类名称
        include_prices: 是否包含价格
        
    Returns:
        格式化的分类菜单字符串
    """
    try:
        items = get_menu_by_category(category_name)
        
        if not items:
            return f"📁 {category_name}: 暂无商品"
        
        lines = [f"📁 **{category_name}**"]
        
        for item in items[:10]:  # 限制显示数量
            name = item.get("item_name", "Unknown")
            if include_prices:
                price = item.get("price", 0.0)
                lines.append(f"• {name} - ${price:.2f}")
            else:
                lines.append(f"• {name}")
        
        if len(items) > 10:
            lines.append(f"... 还有 {len(items) - 10} 个商品")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error formatting category '{category_name}': {e}")
        return f"❌ 无法显示分类: {category_name}"

def calculate_order_total(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    计算订单总计
    
    Args:
        items: 订单项目列表
        
    Returns:
        包含各种总计的字典
    """
    try:
        subtotal = 0.0
        total_items = 0
        
        for item in items:
            quantity = int(item.get("quantity", 0))
            price = float(item.get("price", 0))
            item_total = quantity * price
            
            subtotal += item_total
            total_items += quantity
        
        # 计算税费 (11% - 波多黎各标准税率)
        tax_rate = float(os.getenv("TAX_RATE", "0.11"))
        tax_amount = subtotal * tax_rate
        
        # 最终总计
        total = subtotal + tax_amount
        
        return {
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "tax_rate": tax_rate,
            "total": total,
            "total_items": total_items
        }
        
    except Exception as e:
        logger.error(f"Error calculating order total: {e}")
        return {
            "subtotal": 0.0,
            "tax_amount": 0.0,
            "tax_rate": 0.0,
            "total": 0.0,
            "total_items": 0
        }

def get_all_categories() -> List[str]:
    """
    获取所有菜单分类名称
    
    Returns:
        分类名称列表
    """
    try:
        menu_data = load_menu_data()
        categories = []
        
        for category in menu_data.get("menu_categories", {}).values():
            if isinstance(category, dict):
                name = category.get("name")
                if name:
                    categories.append(name)
        
        return categories
        
    except Exception as e:
        logger.error(f"Error getting categories: {e}")
        return []

def search_items_by_price_range(min_price: float, max_price: float) -> List[Dict[str, Any]]:
    """
    根据价格范围搜索菜单项目
    
    Args:
        min_price: 最低价格
        max_price: 最高价格
        
    Returns:
        价格范围内的菜单项目列表
    """
    try:
        menu_data = load_menu_data()
        matching_items = []
        
        for category in menu_data.get("menu_categories", {}).values():
            if isinstance(category, dict) and "items" in category:
                for item in category["items"]:
                    price = item.get("price", 0.0)
                    if min_price <= price <= max_price:
                        matching_items.append(item)
        
        # 按价格排序
        matching_items.sort(key=lambda x: x.get("price", 0))
        
        logger.debug(f"💰 Found {len(matching_items)} items in price range ${min_price:.2f}-${max_price:.2f}")
        
        return matching_items
        
    except Exception as e:
        logger.error(f"Error searching by price range: {e}")
        return []

def get_cache_info() -> Dict[str, Any]:
    """
    获取缓存信息（用于调试和监控）
    
    Returns:
        缓存信息字典
    """
    global _menu_data_cache, _cache_loaded_at
    
    return {
        "cache_exists": _menu_data_cache is not None,
        "cache_loaded_at": _cache_loaded_at.isoformat() if _cache_loaded_at else None,
        "file_path": KB_PATH,
        "file_exists": os.path.exists(KB_PATH),
        "file_size": os.path.getsize(KB_PATH) if os.path.exists(KB_PATH) else 0
    }

def reload_menu_data() -> bool:
    """
    强制重新加载菜单数据
    
    Returns:
        是否成功重新加载
    """
    try:
        logger.info("🔄 Force reloading menu data...")
        load_menu_data(force_reload=True)
        logger.info("✅ Menu data reloaded successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to reload menu data: {e}")
        return False

def get_menu_file_info() -> Dict[str, Any]:
    """
    获取菜单文件信息
    
    Returns:
        文件信息字典
    """
    try:
        if not os.path.exists(KB_PATH):
            return {"exists": False, "path": KB_PATH}
        
        stat = os.stat(KB_PATH)
        return {
            "exists": True,
            "path": KB_PATH,
            "size_bytes": stat.st_size,
            "size_kb": round(stat.st_size / 1024, 2),
            "modified_timestamp": stat.st_mtime,
            "modified_datetime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "readable": os.access(KB_PATH, os.R_OK)
        }
        
    except Exception as e:
        return {
            "exists": False,
            "path": KB_PATH,
            "error": str(e)
        }

def format_order_summary(items: List[Dict[str, Any]]) -> str:
    """
    格式化订单摘要
    
    Args:
        items: 订单项目列表
        
    Returns:
        格式化的订单摘要字符串
    """
    try:
        if not items:
            return "订单为空"
        
        summary_lines = ["📋 **订单摘要:**"]
        
        for item in items:
            name = item.get("item_name", "未知商品")
            quantity = item.get("quantity", 1)
            price = item.get("price", 0.0)
            item_total = quantity * price
            
            summary_lines.append(f"• {quantity}x {name} - ${item_total:.2f}")
        
        # 添加总计信息
        totals = calculate_order_total(items)
        
        summary_lines.extend([
            "",
            f"小计: ${totals['subtotal']:.2f}",
            f"税费 ({totals['tax_rate']*100:.0f}%): ${totals['tax_amount']:.2f}",
            f"**总计: ${totals['total']:.2f}**",
            f"共 {totals['total_items']} 件商品"
        ])
        
        return "\n".join(summary_lines)
        
    except Exception as e:
        logger.error(f"Error formatting order summary: {e}")
        return "订单摘要生成失败"

def search_items_containing_ingredient(ingredient: str) -> List[Dict[str, Any]]:
    """
    搜索包含特定配料的菜单项目
    
    Args:
        ingredient: 配料名称
        
    Returns:
        包含该配料的菜单项目列表
    """
    try:
        # 使用搜索功能，扩大搜索范围
        candidates = search_menu(ingredient, limit=20)
        
        # 进一步过滤包含该配料的项目
        matching_items = []
        normalized_ingredient = normalize_text(ingredient)
        
        for item in candidates:
            # 检查项目名称
            item_name = normalize_text(item.get("item_name", ""))
            if normalized_ingredient in item_name:
                matching_items.append(item)
                continue
            
            # 检查别名
            aliases = item.get("aliases", [])
            for alias in aliases:
                if normalized_ingredient in normalize_text(alias):
                    matching_items.append(item)
                    break
            
            # 检查关键词
            keywords = item.get("keywords", [])
            for keyword in keywords:
                if normalized_ingredient in normalize_text(keyword):
                    matching_items.append(item)
                    break
        
        logger.debug(f"🥘 Found {len(matching_items)} items containing '{ingredient}'")
        return matching_items
        
    except Exception as e:
        logger.error(f"Error searching items with ingredient '{ingredient}': {e}")
        return []

def get_category_by_item_name(item_name: str) -> Optional[str]:
    """
    根据项目名称获取所属分类
    
    Args:
        item_name: 项目名称
        
    Returns:
        分类名称，如果未找到返回None
    """
    try:
        menu_data = load_menu_data()
        normalized_name = normalize_text(item_name)
        
        for category in menu_data.get("menu_categories", {}).values():
            if isinstance(category, dict) and "items" in category:
                for item in category["items"]:
                    if normalize_text(item.get("item_name", "")) == normalized_name:
                        return category.get("name")
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting category for item '{item_name}': {e}")
        return None

def validate_variant_ids(variant_ids: List[str]) -> Dict[str, bool]:
    """
    验证variant_id列表的有效性
    
    Args:
        variant_ids: variant_id列表
        
    Returns:
        验证结果字典 {variant_id: is_valid}
    """
    try:
        results = {}
        menu_data = load_menu_data()
        
        # 收集所有有效的variant_id
        valid_variant_ids = set()
        for category in menu_data.get("menu_categories", {}).values():
            if isinstance(category, dict) and "items" in category:
                for item in category["items"]:
                    variant_id = item.get("variant_id")
                    if variant_id:
                        valid_variant_ids.add(str(variant_id))
        
        # 验证每个输入的variant_id
        for variant_id in variant_ids:
            results[variant_id] = str(variant_id) in valid_variant_ids
        
        logger.debug(f"🔍 Validated {len(variant_ids)} variant_ids")
        return results
        
    except Exception as e:
        logger.error(f"Error validating variant_ids: {e}")
        return {variant_id: False for variant_id in variant_ids}

def get_menu_health_check() -> Dict[str, Any]:
    """
    菜单系统健康检查
    
    Returns:
        健康检查结果
    """
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "checks": {}
        }
        
        # 检查文件存在性
        file_exists = os.path.exists(KB_PATH)
        health_status["checks"]["file_exists"] = {
            "status": "pass" if file_exists else "fail",
            "path": KB_PATH
        }
        
        if not file_exists:
            health_status["status"] = "unhealthy"
            return health_status
        
        # 检查文件可读性
        file_readable = os.access(KB_PATH, os.R_OK)
        health_status["checks"]["file_readable"] = {
            "status": "pass" if file_readable else "fail"
        }
        
        if not file_readable:
            health_status["status"] = "unhealthy"
            return health_status
        
        # 检查数据加载
        try:
            menu_data = load_menu_data()
            health_status["checks"]["data_loading"] = {
                "status": "pass",
                "stats": get_menu_loading_stats(menu_data)
            }
        except Exception as e:
            health_status["checks"]["data_loading"] = {
                "status": "fail",
                "error": str(e)
            }
            health_status["status"] = "unhealthy"
            return health_status
        
        # 检查数据验证
        validation_result = validate_menu_structure(menu_data)
        health_status["checks"]["data_validation"] = {
            "status": "pass" if validation_result["valid"] else "fail",
            "errors": validation_result.get("errors", [])
        }
        
        if not validation_result["valid"]:
            health_status["status"] = "degraded"
        
        # 检查搜索功能
        try:
            test_results = search_menu("pollo", limit=1)
            health_status["checks"]["search_function"] = {
                "status": "pass",
                "test_results_count": len(test_results)
            }
        except Exception as e:
            health_status["checks"]["search_function"] = {
                "status": "fail",
                "error": str(e)
            }
            health_status["status"] = "degraded"
        
        return health_status
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }
