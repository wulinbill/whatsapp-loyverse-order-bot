#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整的工具模块 - 包含所有必需的函数
"""

import os
import re
import json
import logging
import pathlib
from typing import List, Dict, Any, Optional, Tuple
from fuzzywuzzy import fuzz
import unicodedata

logger = logging.getLogger(__name__)

def load_menu_data() -> Dict[str, Any]:
    """
    加载菜单数据
    
    Returns:
        菜单数据字典
    """
    try:
        # 获取当前文件的目录
        current_dir = pathlib.Path(__file__).parent
        menu_file = current_dir / "data" / "menu_kb.json"
        
        logger.debug(f"Loading menu from: {menu_file}")
        
        if not menu_file.exists():
            logger.error(f"Menu file not found: {menu_file}")
            return {"menu_categories": {}}
        
        with open(menu_file, 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        logger.info(f"✅ Menu data loaded successfully")
        return menu_data
        
    except Exception as e:
        logger.error(f"Failed to load menu data: {e}")
        return {"menu_categories": {}}

def search_menu(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    搜索菜单项目
    
    Args:
        query: 搜索查询
        limit: 返回结果数量限制
        
    Returns:
        匹配的菜单项目列表
    """
    try:
        menu_data = load_menu_data()
        
        # 收集所有菜单项目
        all_items = []
        for category in menu_data.get("menu_categories", {}).values():
            if isinstance(category, dict) and "items" in category:
                all_items.extend(category["items"])
        
        if not all_items:
            logger.warning("No menu items found")
            return []
        
        query_normalized = normalize_text(query)
        scored_items = []
        
        for item in all_items:
            score = calculate_item_score(item, query_normalized)
            if score >= 50:  # 最低匹配阈值
                scored_items.append({
                    "item": item,
                    "score": score
                })
        
        # 按分数排序
        scored_items.sort(key=lambda x: x["score"], reverse=True)
        
        results = [scored_item["item"] for scored_item in scored_items[:limit]]
        
        logger.info(f"🔍 Search for '{query}' found {len(results)} matches")
        
        return results
        
    except Exception as e:
        logger.error(f"Error searching menu for '{query}': {e}")
        return []

def calculate_item_score(item: Dict[str, Any], query_normalized: str) -> float:
    """
    计算项目匹配分数
    
    Args:
        item: 菜单项目
        query_normalized: 标准化的查询字符串
        
    Returns:
        匹配分数
    """
    scores = []
    
    item_name = normalize_text(item.get("item_name", ""))
    
    # 直接名称匹配
    if item_name:
        scores.extend([
            100 if query_normalized == item_name else 0,
            fuzz.partial_ratio(query_normalized, item_name),
            fuzz.ratio(query_normalized, item_name)
        ])
    
    # 别名匹配
    aliases = item.get("aliases", [])
    for alias in aliases:
        normalized_alias = normalize_text(alias)
        if normalized_alias:
            scores.extend([
                100 if query_normalized == normalized_alias else 0,
                fuzz.partial_ratio(query_normalized, normalized_alias),
                fuzz.ratio(query_normalized, normalized_alias)
            ])
    
    # 关键词匹配
    keywords = item.get("keywords", [])
    for keyword in keywords:
        normalized_keyword = normalize_text(keyword)
        if normalized_keyword:
            scores.extend([
                90 if query_normalized == normalized_keyword else 0,
                fuzz.partial_ratio(query_normalized, normalized_keyword)
            ])
    
    return max(scores) if scores else 0

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

def place_loyverse_order(items: List[Dict[str, Any]]) -> str:
    """
    向Loyverse POS系统下单
    
    Args:
        items: 订单项目列表，格式: [{"variant_id": str, "quantity": int, "price": float}]
        
    Returns:
        订单收据编号
        
    Raises:
        Exception: 当下单失败时
    """
    try:
        logger.info(f"📤 Placing order with {len(items)} items to Loyverse")
        
        # 获取环境配置
        store_id = os.getenv("LOYVERSE_STORE_ID")
        pos_device_id = os.getenv("LOYVERSE_POS_DEVICE_ID")
        
        if not store_id or not pos_device_id:
            raise ValueError("Missing Loyverse configuration (STORE_ID or POS_DEVICE_ID)")
        
        # 构建订单负载
        payload = {
            "store_id": store_id,
            "pos_device_id": pos_device_id,
            "line_items": []
        }
        
        # 添加订单项目
        for item in items:
            line_item = {
                "variant_id": str(item["variant_id"]),
                "quantity": int(item["quantity"]),
                "price": float(item["price"])
            }
            payload["line_items"].append(line_item)
        
        # 调用Loyverse API
        from loyverse_api import place_order
        order_response = place_order(payload)
        
        # 提取收据编号
        receipt_number = order_response.get("receipt_number", "unknown")
        
        logger.info(f"✅ Order placed successfully: Receipt #{receipt_number}")
        
        return receipt_number
        
    except Exception as e:
        logger.error(f"❌ Failed to place Loyverse order: {e}")
        raise Exception(f"Failed to place order: {str(e)}")

def calculate_order_total(items: List[Dict[str, Any]]) -> Dict[str, float]:
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

def get_menu_item_by_id(variant_id: str) -> Optional[Dict[str, Any]]:
    """
    根据variant_id获取菜单项目
    
    Args:
        variant_id: 项目变体ID
        
    Returns:
        菜单项目，如果未找到返回None
    """
    try:
        menu_data = load_menu_data()
        
        # 遍历所有菜单项目
        for category in menu_data.get("menu_categories", {}).values():
            if isinstance(category, dict) and "items" in category:
                for item in category["items"]:
                    if item.get("variant_id") == variant_id:
                        return item
        
        logger.warning(f"Menu item not found for variant_id: {variant_id}")
        return None
        
    except Exception as e:
        logger.error(f"Error getting menu item by ID '{variant_id}': {e}")
        return None

def extract_quantity_and_dish_smart(query: str) -> Tuple[int, str, List[str]]:
    """
    智能提取数量、菜品名称和关键词
    
    Args:
        query: 用户查询，如 "2 Combinación de pollo naranja"
        
    Returns:
        (数量, 清理后的菜品名, 关键词列表)
    """
    # 数字映射
    number_words = {
        'uno': 1, 'una': 1, 'un': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5,
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5
    }
    
    query = query.strip().lower()
    quantity = 1
    dish_name = query
    
    # 提取数量
    # 匹配开头的数字
    digit_match = re.match(r'^(\d+)\s+(.+)', query)
    if digit_match:
        quantity = int(digit_match.group(1))
        dish_name = digit_match.group(2).strip()
    else:
        # 匹配开头的文字数字
        for word, num in number_words.items():
            if query.startswith(word + ' '):
                quantity = num
                dish_name = query[len(word):].strip()
                break
    
    # 提取关键词
    keywords = extract_dish_keywords(dish_name)
    
    logger.debug(f"🔍 Extracted: quantity={quantity}, dish='{dish_name}', keywords={keywords}")
    
    return quantity, dish_name, keywords

def extract_dish_keywords(dish_text: str) -> List[str]:
    """
    从菜品文本中提取关键词
    
    Args:
        dish_text: 菜品描述文本
        
    Returns:
        关键词列表，按重要性排序
    """
    keywords = []
    dish_text = dish_text.lower().strip()
    
    # 主要菜品词汇（高优先级）
    main_dishes = {
        'pollo': ['chicken', '鸡', '鸡肉'],
        'carne': ['beef', 'res', '牛肉', '肉'],
        'camarones': ['shrimp', '虾', '虾仁'],
        'arroz': ['rice', '米饭', '饭'],
        'sopa': ['soup', '汤'],
        'tostones': ['plantain', '芭蕉']
    }
    
    # 烹饪方式词汇（中优先级）
    cooking_methods = {
        'teriyaki': ['照烧'],
        'naranja': ['orange', '橙味', '橙'],
        'agridulce': ['sweet sour', 'sweet and sour', '糖醋', '酸甜'],
        'ajillo': ['garlic', '蒜', '蒜蓉'],
        'plancha': ['grilled', '烤', '铁板'],
        'frito': ['fried', '炸'],
        'brocoli': ['broccoli', '西兰花']
    }
    
    # 类型词汇（中优先级）
    dish_types = {
        'combinacion': ['combo', '套餐', '组合'],
        'combinaciones': ['combos', '套餐'],
        'mini': ['small', '小', '小份'],
        'presa': ['piece', 'pieces', '块', '件']
    }
    
    # 按优先级查找关键词
    # 1. 主菜词汇
    for main_word, synonyms in main_dishes.items():
        if main_word in dish_text or any(syn in dish_text for syn in synonyms):
            keywords.append(main_word)
    
    # 2. 烹饪方式
    for cooking_word, synonyms in cooking_methods.items():
        if cooking_word in dish_text or any(syn in dish_text for syn in synonyms):
            keywords.append(cooking_word)
    
    # 3. 类型词汇
    for type_word, synonyms in dish_types.items():
        if type_word in dish_text or any(syn in dish_text for syn in synonyms):
            keywords.append(type_word)
    
    # 4. 提取数字（如"2 presa"）
    numbers = re.findall(r'\d+', dish_text)
    keywords.extend(numbers)
    
    return keywords

def validate_menu_data() -> Dict[str, Any]:
    """
    验证菜单数据的完整性
    
    Returns:
        验证结果字典
    """
    try:
        menu_data = load_menu_data()
        
        total_items = 0
        categories = []
        items_with_price = 0
        items_with_variant_id = 0
        
        for category_key, category_data in menu_data.get("menu_categories", {}).items():
            if isinstance(category_data, dict):
                category_name = category_data.get("name", category_key)
                categories.append(category_name)
                
                items = category_data.get("items", [])
                total_items += len(items)
                
                for item in items:
                    if item.get("price", 0) > 0:
                        items_with_price += 1
                    if item.get("variant_id"):
                        items_with_variant_id += 1
        
        return {
            "status": "healthy",
            "total_categories": len(categories),
            "total_items": total_items,
            "items_with_price": items_with_price,
            "items_with_variant_id": items_with_variant_id,
            "categories": categories[:5]  # 只显示前5个类别
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

def search_menu_by_category(category_name: str) -> List[Dict[str, Any]]:
    """
    按类别搜索菜单项目
    
    Args:
        category_name: 类别名称
        
    Returns:
        该类别的所有菜单项目
    """
    try:
        menu_data = load_menu_data()
        
        for category_data in menu_data.get("menu_categories", {}).values():
            if isinstance(category_data, dict):
                if (category_data.get("name", "").lower() == category_name.lower() or
                    category_name.lower() in category_data.get("name", "").lower()):
                    
                    items = category_data.get("items", [])
                    logger.info(f"📂 Found {len(items)} items in category '{category_name}'")
                    return items
        
        logger.warning(f"Category '{category_name}' not found")
        return []
        
    except Exception as e:
        logger.error(f"Error searching category '{category_name}': {e}")
        return []

def get_popular_items(limit: int = 5) -> List[Dict[str, Any]]:
    """
    获取热门菜品（基于价格范围和类别）
    
    Args:
        limit: 返回数量限制
        
    Returns:
        热门菜品列表
    """
    try:
        # 获取主要类别的代表性菜品
        popular_categories = ["Combinaciones", "MINI Combinaciones", "Pollo Frito"]
        popular_items = []
        
        for category in popular_categories:
            items = search_menu_by_category(category)
            if items:
                # 按价格排序，取中等价位的项目
                sorted_items = sorted(items, key=lambda x: x.get("price", 0))
                if sorted_items:
                    # 取中间价位的项目作为代表
                    mid_index = len(sorted_items) // 2
                    popular_items.append(sorted_items[mid_index])
        
        return popular_items[:limit]
        
    except Exception as e:
        logger.error(f"Error getting popular items: {e}")
        return []

def format_menu_display(items: List[Dict[str, Any]]) -> str:
    """
    格式化菜单显示
    
    Args:
        items: 菜单项目列表
        
    Returns:
        格式化的菜单字符串
    """
    if not items:
        return "未找到菜单项目"
    
    formatted_lines = []
    
    for item in items:
        name = item.get("item_name", "未知菜品")
        price = item.get("price", 0)
        category = item.get("category_name", "")
        
        line = f"• **{name}** - ${price:.2f}"
        if category:
            line += f" ({category})"
        
        formatted_lines.append(line)
    
    return "\n".join(formatted_lines)
