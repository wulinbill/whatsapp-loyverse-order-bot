def check_for_menu_disambiguation(text: str) -> Dict[str, Any]:
    """
    检查是否需要菜单消歧 - 修复版本
    
    Args:
        text: 用户消息
        
    Returns:
        消歧检查结果
    """
    try:
        # 使用新的智能搜索
        from tools import search_menu_smart, debug_search_process
        
        # 提取主要查询
        text_clean = text.strip().lower()
        
        # 跳过太短或非菜品的查询
        if len(text_clean) < 3:
            return {"needs_disambiguation": False}
        
        # 跳过明显的确认词汇
        confirmation_words = ["si", "sí", "ok", "no", "gracias", "listo"]
        if text_clean in confirmation_words:
            return {"needs_disambiguation": False}
        
        logger.debug(f"🔍 Checking disambiguation for: '{text}'")
        
        # 使用智能搜索
        candidates = search_menu_smart(text, limit=10)
        
        # 调试信息
        debug_info = debug_search_process(text)
        logger.debug(f"🔍 Search debug: {debug_info}")
        
        if not candidates:
            return {"needs_disambiguation": False}
        
        # 如果只有一个明确匹配，不需要消歧
        if len(candidates) == 1:
            return {
                "needs_disambiguation": False,
                "single_match": candidates[0]
            }
        
        # 检查是否有明确的最佳匹配
        best_match = find_best_match_for_query(text, candidates)
        if best_match:
            return {
                "needs_disambiguation": False,
                "best_match": best_match,
                "reason": "clear_best_match"
            }
        
        # 需要消歧 - 按类别分组
        by_category = group_candidates_by_category(candidates)
        
        # 过滤相关的候选项
        relevant_candidates = filter_relevant_candidates(text, candidates)
        
        if len(relevant_candidates) <= 1:
            return {"needs_disambiguation": False}
        
        return {
            "needs_disambiguation": True,
            "original_query": text,
            "candidates": relevant_candidates,
            "by_category": group_candidates_by_category(relevant_candidates),
            "debug_info": debug_info
        }
        
    except Exception as e:
        logger.error(f"Error in menu disambiguation check: {e}")
        return {"needs_disambiguation": False}

def find_best_match_for_query(query: str, candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    为查询找到最佳匹配
    
    Args:
        query: 用户查询
        candidates: 候选项目列表
        
    Returns:
        最佳匹配项目，如果没有明确的最佳匹配返回None
    """
    try:
        query_lower = query.lower().strip()
        
        # 特殊处理：明确的菜品名称
        exact_matches = {
            'pollo naranja': 'Pollo Naranja',
            'pollo teriyaki': 'Pollo Teriyaki', 
            'pollo agridulce': 'Pollo Agridulce',
            'pollo ajillo': 'Pollo al Ajillo',
            'pollo plancha': 'Pollo a la Plancha',
            'pepper steak': 'Pepper Steak',
            'pepper pollo': 'Pepper Pollo',
            'brocoli carne': 'Brocoli con Carne de Res'
        }
        
        # 检查查询中是否包含这些关键组合
        for key_phrase, target_name in exact_matches.items():
            if key_phrase in query_lower:
                # 在候选项中查找匹配的项目
                for candidate in candidates:
                    if target_name.lower() in candidate.get("item_name", "").lower():
                        logger.info(f"🎯 Found exact match: '{target_name}' for query '{query}'")
                        return candidate
        
        # 检查是否有压倒性的高分匹配
        if candidates:
            # 这里可以添加更复杂的最佳匹配逻辑
            first_candidate = candidates[0]
            
            # 如果第一个候选项的名称与查询高度匹配
            similarity = fuzz.ratio(query_lower, first_candidate.get("item_name", "").lower())
            if similarity >= 85:
                logger.info(f"🎯 High similarity match ({similarity}%): {first_candidate.get('item_name')}")
                return first_candidate
        
        return None
        
    except Exception as e:
        logger.error(f"Error finding best match: {e}")
        return None

def filter_relevant_candidates(query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    过滤相关的候选项
    
    Args:
        query: 用户查询
        candidates: 候选项目列表
        
    Returns:
        过滤后的相关候选项
    """
    try:
        query_lower = query.lower()
        relevant = []
        
        # 提取查询中的关键词
        query_keywords = []
        if 'pollo' in query_lower:
            query_keywords.append('pollo')
        if 'naranja' in query_lower:
            query_keywords.append('naranja')
        if 'combinacion' in query_lower:
            query_keywords.append('combinacion')
        if 'mini' in query_lower:
            query_keywords.append('mini')
        if 'presa' in query_lower:
            query_keywords.append('presa')
        
        for candidate in candidates:
            item_name = candidate.get("item_name", "").lower()
            category_name = candidate.get("category_name", "").lower()
            
            # 检查是否与查询相关
            is_relevant = False
            
            # 如果查询包含主要关键词，候选项也应该包含
            if query_keywords:
                matching_keywords = sum(1 for kw in query_keywords if kw in item_name or kw in category_name)
                if matching_keywords >= len(query_keywords) * 0.5:  # 至少50%的关键词匹配
                    is_relevant = True
            else:
                # 如果没有明确关键词，使用模糊匹配
                similarity = fuzz.partial_ratio(query_lower, item_name)
                if similarity >= 60:
                    is_relevant = True
            
            if is_relevant:
                relevant.append(candidate)
        
        # 限制数量，避免选项过多
        return relevant[:5]
        
    except Exception as e:
        logger.error(f"Error filtering candidates: {e}")
        return candidates[:5]

def group_candidates_by_category(candidates: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    按类别分组候选项
    
    Args:
        candidates: 候选项目列表
        
    Returns:
        按类别分组的字典
    """
    by_category = {}
    
    for candidate in candidates:
        category = candidate.get("category_name", "Other")
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(candidate)
    
    return by_category

def handle_menu_disambiguation(disambiguation_result: Dict[str, Any]) -> str:
    """
    处理菜单消歧 - 改进版本
    
    Args:
        disambiguation_result: 消歧结果
        
    Returns:
        消歧响应消息
    """
    try:
        original_query = disambiguation_result.get("original_query", "")
        candidates = disambiguation_result.get("candidates", [])
        
        if not candidates:
            return f"No encontré '{original_query}' en nuestro menú. ¿Podría ser más específico?"
        
        # 构建消歧响应
        response_lines = [f"Tenemos estas opciones para '{original_query}':"]
        response_lines.append("")
        
        # 直接显示候选项（不按类别分组，避免混淆）
        for i, item in enumerate(candidates[:5], 1):
            name = item.get("item_name", "Unknown")
            price = item.get("price", 0.0)
            category = item.get("category_name", "")
            
            # 添加类别信息帮助用户理解
            if category:
                response_lines.append(f"{i}. **{name}** (${price:.2f}) - {category}")
            else:
                response_lines.append(f"{i}. **{name}** (${price:.2f})")
        
        response_lines.append("")
        response_lines.append("¿Cuál prefiere? Puede decir el número o el nombre completo.")
        
        return "\n".join(response_lines)
        
    except Exception as e:
        logger.error(f"Error handling menu disambiguation: {e}")
        return "Hubo un error mostrando las opciones. ¿Podría repetir su pedido?"
