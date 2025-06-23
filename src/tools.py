#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复后的菜单搜索逻辑
重点修复: 准确识别"2 Combinación de pollo naranja"等复合查询
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from fuzzywuzzy import fuzz
import unicodedata

logger = logging.getLogger(__name__)

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

def search_menu_smart(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    智能菜单搜索 - 专门处理复合查询
    
    Args:
        query: 搜索查询
        limit: 返回结果数量限制
        
    Returns:
        匹配的菜单项目列表，按相关性排序
    """
    try:
        # 加载菜单数据
        from tools import load_menu_data  # 使用现有的加载函数
        menu_data = load_menu_data()
        
        # 智能解析查询
        quantity, dish_name, keywords = extract_quantity_and_dish_smart(query)
        
        logger.info(f"🔍 Smart search for: '{query}' -> quantity={quantity}, dish='{dish_name}', keywords={keywords}")
        
        # 收集所有菜单项目
        all_items = []
        for category in menu_data.get("menu_categories", {}).values():
            if isinstance(category, dict) and "items" in category:
                all_items.extend(category["items"])
        
        if not all_items:
            logger.warning("No menu items found")
            return []
        
        # 计算匹配分数
        scored_items = []
        
        for item in all_items:
            scores = calculate_smart_item_scores(item, dish_name, keywords)
            max_score = max(scores.values()) if scores else 0
            
            if max_score >= 50:  # 降低阈值，提高匹配率
                scored_items.append({
                    "item": item,
                    "score": max_score,
                    "match_details": scores
                })
        
        # 按分数排序
        scored_items.sort(key=lambda x: x["score"], reverse=True)
        
        # 特殊处理：如果查询包含明确的菜品名称，优先匹配
        if len(keywords) >= 2:  # 有足够的关键词
            prioritized_items = prioritize_exact_matches(scored_items, keywords)
            if prioritized_items:
                scored_items = prioritized_items
        
        # 返回结果
        results = [scored_item["item"] for scored_item in scored_items[:limit]]
        
        logger.info(f"✅ Smart search found {len(results)} matches for '{query}'")
        for i, item in enumerate(results[:3]):
            logger.debug(f"  {i+1}. {item.get('item_name')} (score: {scored_items[i]['score']})")
        
        return results
        
    except Exception as e:
        logger.error(f"Error in smart menu search for '{query}': {e}")
        return []

def calculate_smart_item_scores(item: Dict[str, Any], dish_name: str, keywords: List[str]) -> Dict[str, float]:
    """
    计算智能匹配分数
    
    Args:
        item: 菜单项目
        dish_name: 清理后的菜品名称
        keywords: 关键词列表
        
    Returns:
        匹配分数字典
    """
    scores = {}
    
    item_name = normalize_text(item.get("item_name", ""))
    category_name = normalize_text(item.get("category_name", ""))
    
    # 1. 直接名称匹配
    if item_name:
        scores["name_exact"] = 100 if normalize_text(dish_name) == item_name else 0
        scores["name_partial"] = fuzz.partial_ratio(normalize_text(dish_name), item_name)
        scores["name_ratio"] = fuzz.ratio(normalize_text(dish_name), item_name)
    
    # 2. 关键词组合匹配（重要！）
    if keywords:
        keyword_scores = []
        
        for keyword in keywords:
            normalized_keyword = normalize_text(keyword)
            
            # 在项目名称中查找关键词
            if normalized_keyword in item_name:
                keyword_scores.append(90)  # 高分
            elif any(normalized_keyword in alias for alias in item.get("aliases", [])):
                keyword_scores.append(85)
            elif any(normalized_keyword in kw for kw in item.get("keywords", [])):
                keyword_scores.append(80)
            else:
                # 模糊匹配
                name_similarity = fuzz.partial_ratio(normalized_keyword, item_name)
                if name_similarity > 70:
                    keyword_scores.append(name_similarity)
        
        if keyword_scores:
            # 关键词匹配的综合分数
            scores["keyword_combo"] = sum(keyword_scores) / len(keywords)
            
            # 如果多个关键词都匹配，给额外奖励
            if len(keyword_scores) >= 2:
                scores["multi_keyword_bonus"] = min(95, scores["keyword_combo"] + 10)
    
    # 3. 别名匹配
    aliases = item.get("aliases", [])
    if aliases:
        alias_scores = []
        for alias in aliases:
            normalized_alias = normalize_text(alias)
            if normalized_alias:
                alias_scores.extend([
                    100 if normalize_text(dish_name) == normalized_alias else 0,
                    fuzz.partial_ratio(normalize_text(dish_name), normalized_alias),
                    fuzz.ratio(normalize_text(dish_name), normalized_alias)
                ])
        if alias_scores:
            scores["alias_best"] = max(alias_scores)
    
    # 4. 类别相关性匹配
    if category_name and any(kw in category_name for kw in ['combinacion', 'combo', 'mini']):
        if any(kw in keywords for kw in ['combinacion', 'combinaciones', 'combo']):
            scores["category_match"] = 75
    
    return scores

def prioritize_exact_matches(scored_items: List[Dict], keywords: List[str]) -> List[Dict]:
    """
    优先处理精确匹配的项目
    
    Args:
        scored_items: 评分后的项目列表
        keywords: 关键词列表
        
    Returns:
        重新排序的项目列表
    """
    # 特殊逻辑：如果有"pollo"和"naranja"关键词，优先匹配"Pollo Naranja"
    if 'pollo' in keywords and 'naranja' in keywords:
        pollo_naranja_items = []
        other_items = []
        
        for scored_item in scored_items:
            item_name = normalize_text(scored_item["item"].get("item_name", ""))
            if 'pollo' in item_name and 'naranja' in item_name:
                pollo_naranja_items.append(scored_item)
            else:
                other_items.append(scored_item)
        
        # 将Pollo Naranja项目排在前面
        return pollo_naranja_items + other_items
    
    return scored_items

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

def debug_search_process(query: str) -> Dict[str, Any]:
    """
    调试搜索过程
    
    Args:
        query: 搜索查询
        
    Returns:
        调试信息字典
    """
    quantity, dish_name, keywords = extract_quantity_and_dish_smart(query)
    results = search_menu_smart(query, limit=5)
    
    debug_info = {
        "original_query": query,
        "extracted_quantity": quantity,
        "extracted_dish_name": dish_name,
        "extracted_keywords": keywords,
        "results_count": len(results),
        "results": []
    }
    
    for result in results:
        debug_info["results"].append({
            "item_name": result.get("item_name"),
            "category_name": result.get("category_name"),
            "price": result.get("price")
        })
    
    return debug_info
