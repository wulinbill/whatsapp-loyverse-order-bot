#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
订单处理模块
将自然语言订单转换为POS系统格式
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from tools import search_menu, get_menu_item_by_id

logger = logging.getLogger(__name__)

def extract_quantity_and_item(sentence: str) -> Tuple[int, str]:
    """
    从句子中提取数量和物品名称
    
    Args:
        sentence: 输入句子，如 "2 pollo teriyaki" 或 "tres tostones"
        
    Returns:
        (数量, 物品名称) 元组
    """
    sentence = sentence.strip()
    
    # 数字词汇映射
    number_words = {
        'uno': 1, 'una': 1, 'un': 1,
        'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5,
        'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10,
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
    }
    
    # 尝试匹配开头的数字
    digit_match = re.match(r'^(\d+)\s+(.+)', sentence)
    if digit_match:
        quantity = int(digit_match.group(1))
        item_name = digit_match.group(2).strip()
        logger.debug(f"📊 Extracted quantity from digits: {quantity}x {item_name}")
        return quantity, item_name
    
    # 尝试匹配数字词汇
    for word, num in number_words.items():
        pattern = rf'^{re.escape(word)}\s+(.+)'
        word_match = re.match(pattern, sentence, re.IGNORECASE)
        if word_match:
            quantity = num
            item_name = word_match.group(1).strip()
            logger.debug(f"📊 Extracted quantity from word '{word}': {quantity}x {item_name}")
            return quantity, item_name
    
    # 默认数量为1
    logger.debug(f"📊 No quantity found, defaulting to 1x {sentence}")
    return 1, sentence

def convert(sentences: List[str]) -> List[Dict]:
    """
    将句子列表转换为订单项目
    
    Args:
        sentences: 订单句子列表
        
    Returns:
        订单项目列表，格式为 [{"variant_id": str, "quantity": int, "price": float}]
    """
    order_items = []
    
    logger.info(f"🔄 Converting {len(sentences)} sentences to order items")
    
    for i, sentence in enumerate(sentences):
        if not sentence or not sentence.strip():
            logger.debug(f"⏭️ Skipping empty sentence {i}")
            continue
            
        try:
            # 提取数量和物品名称
            quantity, item_name = extract_quantity_and_item(sentence)
            
            # 清理物品名称
            cleaned_name = clean_item_name(item_name)
            
            # 搜索菜单项目
            candidates = search_menu(cleaned_name, limit=1)
            
            if candidates:
                item = candidates[0]
                
                # 构建订单项目
                order_item = {
                    "variant_id": item["variant_id"],
                    "quantity": quantity,
                    "price": item["price"],
                    "item_name": item["item_name"]  # 用于确认消息
                }
                
                order_items.append(order_item)
                
                logger.info(f"✅ Added to order: {quantity}x {item['item_name']} (${item['price']:.2f})")
                
            else:
                logger.warning(f"❌ No menu item found for: '{cleaned_name}' (original: '{sentence}')")
                
                # 可以在这里添加建议逻辑
                suggestions = get_item_suggestions(cleaned_name)
                if suggestions:
                    logger.info(f"💡 Suggestions for '{cleaned_name}': {suggestions}")
                
        except Exception as e:
            logger.error(f"❌ Error processing sentence '{sentence}': {e}")
    
    logger.info(f"🎯 Successfully converted {len(order_items)} items")
    return order_items

def clean_item_name(name: str) -> str:
    """
    清理物品名称，移除干扰词汇
    
    Args:
        name: 原始物品名称
        
    Returns:
        清理后的名称
    """
    # 移除常见的连接词和修饰词
    stop_words = [
        'con', 'de', 'del', 'la', 'el', 'y', 'en', 'para', 'por', 'sin',
        'with', 'and', 'the', 'a', 'an', 'in', 'on', 'for', 'without',
        '的', '和', '与', '及', '或'
    ]
    
    # 分割单词
    words = name.split()
    
    # 过滤停用词（保持原有意义）
    filtered_words = []
    for word in words:
        # 保留重要的菜品词汇
        if word.lower() not in stop_words or len(filtered_words) == 0:
            filtered_words.append(word)
    
    cleaned = ' '.join(filtered_words).strip()
    
    if cleaned != name:
        logger.debug(f"🧹 Cleaned item name: '{name}' → '{cleaned}'")
    
    return cleaned

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

def validate_order(items: List[Dict]) -> Tuple[bool, List[str]]:
    """
    验证订单项目
    
    Args:
        items: 订单项目列表
        
    Returns:
        (是否有效, 错误信息列表)
    """
    errors = []
    
    if not items:
        errors.append("订单为空")
        return False, errors
    
    for i, item in enumerate(items):
        # 检查必要字段
        required_fields = ["variant_id", "quantity", "price"]
        for field in required_fields:
            if field not in item:
                errors.append(f"订单项目 {i+1} 缺少字段: {field}")
        
        # 验证数量
        try:
            quantity = int(item.get("quantity", 0))
            if quantity <= 0:
                errors.append(f"订单项目 {i+1} 数量必须大于0")
            elif quantity > 50:  # 合理的数量上限
                errors.append(f"订单项目 {i+1} 数量过大: {quantity}")
        except (ValueError, TypeError):
            errors.append(f"订单项目 {i+1} 数量格式无效")
        
        # 验证价格
        try:
            price = float(item.get("price", 0))
            if price < 0:
                errors.append(f"订单项目 {i+1} 价格不能为负数")
            elif price > 1000:  # 合理的价格上限
                errors.append(f"订单项目 {i+1} 价格异常高: ${price:.2f}")
        except (ValueError, TypeError):
            errors.append(f"订单项目 {i+1} 价格格式无效")
        
        # 验证variant_id
        variant_id = item.get("variant_id")
        if not variant_id or not str(variant_id).strip():
            errors.append(f"订单项目 {i+1} variant_id 无效")
    
    is_valid = len(errors) == 0
    return is_valid, errors

def calculate_order_total(items: List[Dict]) -> Dict[str, float]:
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

def format_order_summary(items: List[Dict]) -> str:
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

def process_order_modifications(base_items: List[Dict], modifications: List[str]) -> List[Dict]:
    """
    处理订单修改（添加、删除、更改数量等）
    
    Args:
        base_items: 基础订单项目
        modifications: 修改指令列表
        
    Returns:
        修改后的订单项目列表
    """
    try:
        modified_items = base_items.copy()
        
        for mod in modifications:
            mod = mod.strip().lower()
            
            # 处理添加操作
            if any(word in mod for word in ['add', 'añadir', '加', 'agregar']):
                add_items = convert([mod])
                modified_items.extend(add_items)
                logger.info(f"➕ Added items from modification: {mod}")
            
            # 处理删除操作
            elif any(word in mod for word in ['remove', 'delete', 'quitar', '删除', 'eliminar']):
                # 这里可以实现删除逻辑
                logger.info(f"➖ Remove operation: {mod}")
                # 简单实现：移除最后一个匹配的项目
                
            # 处理数量变更
            elif any(word in mod for word in ['change', 'cambiar', '改', 'modify']):
                logger.info(f"🔄 Quantity change: {mod}")
                # 这里可以实现数量变更逻辑
        
        return modified_items
        
    except Exception as e:
        logger.error(f"Error processing order modifications: {e}")
        return base_items

def extract_special_instructions(sentences: List[str]) -> Tuple[List[str], List[str]]:
    """
    从句子中提取特殊说明和普通订单项目
    
    Args:
        sentences: 原始句子列表
        
    Returns:
        (订单项目句子, 特殊说明句子) 元组
    """
    order_sentences = []
    special_instructions = []
    
    # 特殊说明关键词
    instruction_keywords = [
        'sin', 'without', 'no', '不要', '没有',
        'extra', 'más', '加', '多',
        'poco', 'less', '少', '轻',
        'aparte', 'separate', '分开',
        'caliente', 'hot', '热',
        'frío', 'cold', '冷'
    ]
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        # 检查是否包含特殊说明关键词
        is_instruction = any(keyword in sentence.lower() for keyword in instruction_keywords)
        
        if is_instruction:
            special_instructions.append(sentence)
            logger.debug(f"🔔 Special instruction: {sentence}")
        else:
            order_sentences.append(sentence)
            logger.debug(f"🍽️ Order item: {sentence}")
    
    return order_sentences, special_instructions

def apply_combo_rules(items: List[Dict]) -> List[Dict]:
    """
    应用套餐规则（如Combinaciones默认包含rice+papa）
    
    Args:
        items: 原始订单项目
        
    Returns:
        应用规则后的订单项目
    """
    try:
        processed_items = []
        
        for item in items:
            processed_items.append(item)
            
            # 检查是否是Combinaciones类别
            item_name = item.get("item_name", "").lower()
            
            if "combinacion" in item_name or "combo" in item_name:
                logger.info(f"🍱 Applying combo rules for: {item['item_name']}")
                
                # 这里可以添加自动添加rice+papa的逻辑
                # 但需要先检查用户是否已经指定了其他配菜
                
        return processed_items
        
    except Exception as e:
        logger.error(f"Error applying combo rules: {e}")
        return items

import os  # 需要导入os模块用于税率计算