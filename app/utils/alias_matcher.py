import time
from typing import List, Dict, Any, Tuple
from rapidfuzz import fuzz, process
import json
import os
import re

from ..config import get_settings
from ..logger import get_logger, business_logger

settings = get_settings()
logger = get_logger(__name__)

class AliasMatcher:
    """基于RapidFuzz的菜单项匹配器 - 修复版本，减少误匹配"""
    
    def __init__(self):
        self.menu_items = []
        self.search_index = {}
        # 按照最新文档要求，使用80作为token_set_ratio的阈值
        self.token_set_ratio_threshold = 80
        self.general_threshold = settings.fuzzy_match_threshold  # 保留原配置用于其他匹配
        self._load_menu_data()
        self._build_search_index()
    
    def _load_menu_data(self):
        """加载菜单数据"""
        try:
            # 获取菜单文件路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            menu_file_paths = [
                os.path.join(current_dir, "..", "knowledge_base", "menu_kb.json"),
                os.path.join(current_dir, "..", "..", "knowledge_base", "menu_kb.json"),
                "app/knowledge_base/menu_kb.json",
                "knowledge_base/menu_kb.json"
            ]
            
            menu_data = None
            for menu_file in menu_file_paths:
                if os.path.exists(menu_file):
                    with open(menu_file, 'r', encoding='utf-8') as f:
                        menu_data = json.load(f)
                    logger.info(f"Loaded menu data from: {menu_file}")
                    break
            
            if not menu_data:
                logger.error("menu_kb.json not found")
                self.menu_items = []
                return
            
            # 提取所有菜单项
            self.menu_items = []
            for category_name, category_data in menu_data.get("menu_categories", {}).items():
                if isinstance(category_data, dict) and "items" in category_data:
                    for item in category_data["items"]:
                        # 确保每个item都有category_name
                        item["category_name"] = category_name
                        self.menu_items.append(item)
            
            logger.info(f"Loaded {len(self.menu_items)} menu items for matching")
            
        except Exception as e:
            logger.error(f"Failed to load menu data: {e}")
            self.menu_items = []
    
    def _build_search_index(self):
        """构建搜索索引"""
        self.search_index = {}
        
        for item in self.menu_items:
            item_id = item.get("item_id", "")
            
            # 索引项目名称
            item_name = item.get("item_name", "")
            if item_name:
                self.search_index[item_name.lower()] = item
            
            # 索引别名
            for alias in item.get("aliases", []):
                if alias:
                    self.search_index[alias.lower()] = item
            
            # 索引关键词
            for keyword in item.get("keywords", []):
                if keyword:
                    self.search_index[keyword.lower()] = item
            
            # 索引SKU
            sku = item.get("sku", "")
            if sku:
                self.search_index[sku.lower()] = item
        
        logger.info(f"Built search index with {len(self.search_index)} entries")
    
    def find_matches(self, query: str, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        查找匹配的菜单项 - 修复版本，减少误匹配
        """
        start_time = time.time()
        
        try:
            query_lower = query.lower().strip()
            
            if not query_lower:
                return []
            
            logger.info(f"Starting menu search for '{query}' (user: {user_id})")
            
            # 预处理查询
            processed_query = self._preprocess_query(query_lower)
            logger.info(f"Processed query: '{processed_query}'")
            
            matches = []
            
            # 1. 首先尝试精确匹配（100分）
            exact_matches = self._find_exact_matches(processed_query)
            matches.extend(exact_matches)
            
            # 2. 然后进行token_set_ratio模糊匹配（≥80分）
            if len(matches) < limit:
                fuzzy_matches = self._find_token_set_ratio_matches(processed_query, limit - len(matches))
                matches.extend(fuzzy_matches)
            
            # 3. 去重并排序
            matches = self._deduplicate_and_sort(matches)
            
            # 4. 应用更严格的验证规则
            validated_matches = []
            for match in matches:
                if self._is_valid_match(query_lower, match.get("item_name", ""), match.get("category_name", "")):
                    validated_matches.append(match)
                else:
                    logger.debug(f"Rejected match: {match.get('item_name')} - failed validation")
            
            # 5. 按照新流程要求：只返回≥80分的匹配
            high_quality_matches = [m for m in validated_matches if m.get("score", 0) >= self.token_set_ratio_threshold]
            
            # 6. 应用智能过滤，减少误匹配
            filtered_matches = self._smart_filter_matches(query_lower, high_quality_matches)[:limit]
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 记录匹配日志
            business_logger.log_menu_match(
                user_id=user_id,
                query=query,
                matches=filtered_matches,
                method="rapidfuzz_token_set_ratio",
                duration_ms=duration_ms
            )
            
            # 记录匹配成功/失败和具体结果
            if filtered_matches:
                logger.info(f"RapidFuzz SUCCESS for '{query}': found {len(filtered_matches)} matches ≥80")
                for i, match in enumerate(filtered_matches[:3]):
                    logger.info(f"  Match {i+1}: {match.get('item_name')} (score: {match.get('score')}, category: {match.get('category_name')})")
            else:
                logger.info(f"RapidFuzz FAILED for '{query}': no matches ≥80 (will fallback to Claude)")
            
            return filtered_matches
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="match",
                error_code="RAPIDFUZZ_MATCH_FAILED",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"RapidFuzz ERROR for '{query}': {e}")
            return []
    
    def _preprocess_query(self, query: str) -> str:
        """预处理查询，标准化格式"""
        # 移除多余空格
        query = re.sub(r'\s+', ' ', query.strip())
        
        # 标准化常见变体
        replacements = {
            'grandes': 'grande',
            'medianos': 'mediano',
            'pequeños': 'pequeño',
            'combinaciones': 'combinación',
            'combos': 'combo'
        }
        
        for old, new in replacements.items():
            query = re.sub(rf'\b{old}\b', new, query)
        
        return query
    
    def _find_exact_matches(self, query: str) -> List[Dict[str, Any]]:
        """查找精确匹配"""
        matches = []
        
        for key, item in self.search_index.items():
            if query == key:
                match_item = item.copy()
                match_item["score"] = 100.0  # 精确匹配给最高分
                match_item["match_type"] = "exact"
                match_item["match_key"] = key
                matches.append(match_item)
        
        return matches
    
    def _find_token_set_ratio_matches(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """使用token_set_ratio进行模糊匹配 - 按照新流程要求"""
        matches = []
        
        # 使用token_set_ratio进行匹配，对词序不敏感
        search_keys = list(self.search_index.keys())
        fuzzy_results = process.extract(
            query, 
            search_keys, 
            scorer=fuzz.token_set_ratio,  # 明确使用token_set_ratio
            limit=limit * 3,  # 多取一些用于去重和过滤
            score_cutoff=self.token_set_ratio_threshold  # 直接在这里过滤≥80的结果
        )
        
        for match_key, score, _ in fuzzy_results:
            # 双重保险：确保分数≥80
            if score >= self.token_set_ratio_threshold:
                item = self.search_index[match_key].copy()
                item["score"] = float(score)
                item["match_type"] = "token_set_ratio"
                item["match_key"] = match_key
                matches.append(item)
        
        return matches
    
    def _is_valid_match(self, query: str, item_name: str, category: str) -> bool:
        """应用更严格的匹配验证规则"""
        query_lower = query.lower()
        item_lower = item_name.lower()
        category_lower = category.lower()
        
        # 规则1: 如果查询包含"combinación"，只匹配combinaciones类别
        if 'combinación' in query_lower and 'combinaciones' not in category_lower:
            logger.debug(f"Rejecting '{item_name}': query has 'combinación' but item is not in Combinaciones category")
            return False
        
        # 规则2: 如果查询包含"sopa"，只匹配sopas类别
        if 'sopa' in query_lower and 'sopas' not in category_lower:
            logger.debug(f"Rejecting '{item_name}': query has 'sopa' but item is not in Sopas category")
            return False
        
        # 规则3: 防止"pollo"误匹配非鸡肉类菜品
        if 'pollo' in query_lower:
            # 如果查询明确要求pollo，但菜品名称不包含pollo且不是相关类别
            if 'pollo' not in item_lower and not any(cat in category_lower for cat in ['combinaciones', 'pollo']):
                logger.debug(f"Rejecting '{item_name}': query has 'pollo' but item doesn't contain 'pollo' and is not in relevant category")
                return False
        
        # 规则4: 特定调料/风味词的精确匹配 - 重点修复
        flavor_keywords = {
            'naranja': ['naranja', 'orange'],
            'pepper': ['pepper'],
            'sweet': ['sweet', 'dulce'],
            'sour': ['sour', 'agridulce'],
            'teriyaki': ['teriyaki'],
            'general': ['general', 'tso']
        }
        
        for flavor, variants in flavor_keywords.items():
            query_has_flavor = any(variant in query_lower for variant in variants)
            item_has_flavor = any(variant in item_lower for variant in variants)
            
            # 如果查询明确要求某种口味，但菜品没有，则不匹配
            if query_has_flavor and not item_has_flavor:
                logger.debug(f"Rejecting '{item_name}': query requests {flavor} but item doesn't have it")
                return False
            
            # 反之，如果菜品有特定口味但查询没有要求，也要谨慎
            # 例如：查询"pollo"不应该匹配"Pepper Pollo"
            if not query_has_flavor and item_has_flavor and flavor in ['pepper', 'teriyaki']:
                # 检查查询是否足够具体
                if len(query_lower.split()) <= 2:  # 简单查询
                    logger.debug(f"Rejecting '{item_name}': simple query doesn't specify {flavor} but item has it")
                    return False
        
        # 规则5: 特殊情况 - "Combinación pollo naranja" vs "Pepper Pollo"
        if 'combinación' in query_lower and 'naranja' in query_lower:
            if 'pepper' in item_lower and 'combinaciones' not in category_lower:
                logger.debug(f"Rejecting '{item_name}': query wants 'combinación naranja' but item is pepper variant")
                return False
        
        logger.debug(f"Accepting '{item_name}': passed all validation rules")
        return True
    
    def _smart_filter_matches(self, query: str, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """智能过滤匹配结果，减少误匹配"""
        if not matches:
            return []
        
        # 如果有完全匹配或高分匹配，优先返回
        high_score_matches = [m for m in matches if m["score"] >= 95]
        if high_score_matches:
            return high_score_matches
        
        # 按类别分组
        category_groups = {}
        for match in matches:
            category = match.get("category_name", "unknown")
            if category not in category_groups:
                category_groups[category] = []
            category_groups[category].append(match)
        
        # 如果查询明确指向某个类别，只返回该类别的匹配
        if 'combinación' in query and 'Combinaciones' in category_groups:
            return sorted(category_groups['Combinaciones'], key=lambda x: x['score'], reverse=True)[:3]
        elif 'sopa' in query and 'Sopas' in category_groups:
            return sorted(category_groups['Sopas'], key=lambda x: x['score'], reverse=True)[:3]
        
        # 否则返回前几名，但确保类别多样性和质量
        filtered = []
        used_categories = set()
        
        # 按分数排序
        sorted_matches = sorted(matches, key=lambda x: x['score'], reverse=True)
        
        for match in sorted_matches:
            category = match.get("category_name")
            
            # 优先添加高分匹配
            if match['score'] >= 90:
                filtered.append(match)
                used_categories.add(category)
            # 然后添加不同类别的匹配
            elif len(filtered) < 3:
                if category not in used_categories or len(filtered) < 2:
                    filtered.append(match)
                    used_categories.add(category)
            
            if len(filtered) >= 3:
                break
        
        return filtered
    
    def _deduplicate_and_sort(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """去重并排序"""
        # 按item_id去重，保留最高分
        seen_items = {}
        for match in matches:
            item_id = match.get("item_id", "")
            if item_id:
                if item_id not in seen_items or match["score"] > seen_items[item_id]["score"]:
                    seen_items[item_id] = match
        
        # 按分数排序（高分在前）
        result = list(seen_items.values())
        result.sort(key=lambda x: x["score"], reverse=True)
        
        return result
    
    def find_similar_items(self, item_name: str, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """查找相似菜品，用于推荐"""
        try:
            # 提取关键词进行匹配
            keywords = self._extract_keywords(item_name)
            all_matches = []
            
            for keyword in keywords:
                matches = self.find_matches(keyword, user_id, limit)
                all_matches.extend(matches)
            
            # 去重并返回前几个
            return self._deduplicate_and_sort(all_matches)[:limit]
            
        except Exception as e:
            logger.error(f"Error finding similar items: {e}")
            return []
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        keywords = []
        
        # 分割单词
        words = text.lower().split()
        keywords.extend(words)
        
        # 常见的菜品关键词
        food_keywords = [
            "pollo", "carne", "cerdo", "camarones", "arroz", "papa", 
            "tostones", "brocoli", "teriyaki", "agridulce", "plancha",
            "chicken", "beef", "pork", "shrimp", "rice", "potato",
            "sopa", "china", "frita", "combinacion", "combo", "presas"
        ]
        
        for word in words:
            for food_keyword in food_keywords:
                if food_keyword in word or word in food_keyword:
                    keywords.append(food_keyword)
        
        return list(set(keywords))  # 去重
    
    def get_item_by_id(self, item_id: str) -> Dict[str, Any]:
        """根据ID获取菜品信息"""
        for item in self.menu_items:
            if item.get("item_id") == item_id:
                return item
        return {}
    
    def refresh_menu_data(self):
        """刷新菜单数据"""
        logger.info("Refreshing menu data...")
        self._load_menu_data()
        self._build_search_index()
        logger.info("Menu data refreshed successfully")
    
    def get_matching_stats(self) -> Dict[str, Any]:
        """获取匹配统计信息（用于监控和优化）"""
        return {
            "total_menu_items": len(self.menu_items),
            "search_index_size": len(self.search_index),
            "token_set_ratio_threshold": self.token_set_ratio_threshold,
            "general_threshold": self.general_threshold
        }

# 全局别名匹配器实例
alias_matcher = AliasMatcher()
