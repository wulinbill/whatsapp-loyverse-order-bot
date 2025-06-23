#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具函数模块
提供菜单搜索、订单处理等实用功能
"""

import os
import json
import re
import logging
from typing import List, Dict, Optional, Any
from fuzzywuzzy import fuzz, process
import unicodedata
import loyverse_api

logger = logging.getLogger(__name__)

# 菜单数据路径
KB_PATH = os.path.join(os.path.dirname(__file__), "data", "menu_kb.json")

# 全局菜单数据缓存
_menu_data_cache = None

def load_menu_data() -> Dict[str, Any]:
    """
    加载菜单数据（带缓存）
    
    Returns:
        菜单数据字典
    """
    global _menu_data_cache
    
    if _menu_data_cache is None:
        try:
            with open(KB_PATH, 'r', encoding='utf-8') as f:
                _menu_data_cache = json.load(f)
            logger.info(f"📖 Menu data loaded from {KB_PATH}")
        except Exception as e:
            logger.error(f"Failed to load menu data: {e}")
            _menu_data_cache = {"menu_categories": {}}
    
    return _menu_data_cache

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
    向Loyverse POS系统下单
    
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
        
        # 获取register_id
        register_id = os.getenv("LOYVERSE_REGISTER_ID")
        if not register_id:
            raise ValueError("LOYVERSE_REGISTER_ID not configured")
        
        # 构建订单负载
        payload = {
            "register_id": register_id,
            "line_items": [
                {
                    "variant_id": item["variant_id"],
                    "quantity": int(item["quantity"]),
                    "price": int(float(item["price"]) * 100)  # 转换为分
                }
                for item in items
            ]
        }
        
        logger.info(f"📤 Placing order with {len(items)} items")
        
        # 调用Loyverse API
        response = loyverse_api.place_order(payload)
        
        receipt_number = response.get("receipt_number", "unknown")
        
        logger.info(f"✅ Order placed successfully: Receipt #{receipt_number}")
        
        return receipt_number
        
    except Exception as e:
        logger.error(f"Failed to place Loyverse order: {e}")
        raise Exception(f"Failed to place order: {str(e)}")

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