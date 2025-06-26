import time
from typing import List, Dict, Any, Tuple
from rapidfuzz import fuzz, process
import json
import os

from ..config import get_settings
from ..logger import get_logger, business_logger

settings = get_settings()
logger = get_logger(__name__)

class AliasMatcher:
    """基于RapidFuzz的菜单项匹配器"""
    
    def __init__(self):
        self.menu_items = []
        self.search_index = {}
        self.threshold = settings.fuzzy_match_threshold
        self._load_menu_data()
        self._build_search_index()
    
    def _load_menu_data(self):
        """加载菜单数据"""
        try:
            # 获取菜单文件路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            menu_file = os.path.join(current_dir, "..", "knowledge_base", "menu_kb.json")
            
            with open(menu_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 提取所有菜单项
            self.menu_items = []
            for category_name, category_data in data.get("menu_categories", {}).items():
                if isinstance(category_data, dict) and "items" in category_data:
                    for item in category_data["items"]:
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
        查找匹配的菜单项
        
        Args:
            query: 查询字符串
            user_id: 用户ID
            limit: 返回结果数量限制
            
        Returns:
            匹配的菜单项列表，包含相似度分数
        """
        start_time = time.time()
        
        try:
            query_lower = query.lower().strip()
            
            if not query_lower:
                return []
            
            # 使用RapidFuzz进行模糊匹配
            matches = []
            
            # 1. 首先尝试精确匹配
            exact_matches = self._find_exact_matches(query_lower)
            matches.extend(exact_matches)
            
            # 2. 然后进行模糊匹配
            if len(matches) < limit:
                fuzzy_matches = self._find_fuzzy_matches(query_lower, limit - len(matches))
                matches.extend(fuzzy_matches)
            
            # 3. 去重并排序
            matches = self._deduplicate_and_sort(matches)[:limit]
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 记录匹配日志
            business_logger.log_menu_match(
                user_id=user_id,
                query=query,
                matches=matches,
                method="fuzzy_search",
                duration_ms=duration_ms
            )
            
            return matches
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="match",
                error_code="FUZZY_MATCH_FAILED",
                error_msg=str(e),
                exception=e
            )
            return []
    
    def _find_exact_matches(self, query: str) -> List[Dict[str, Any]]:
        """查找精确匹配"""
        matches = []
        
        for key, item in self.search_index.items():
            if query == key:
                match_item = item.copy()
                match_item["score"] = 100.0  # 精确匹配给最高分
                match_item["match_type"] = "exact"
                matches.append(match_item)
        
        return matches
    
    def _find_fuzzy_matches(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """查找模糊匹配"""
        matches = []
        
        # 使用token_set_ratio进行匹配，对词序不敏感
        search_keys = list(self.search_index.keys())
        fuzzy_results = process.extract(
            query, 
            search_keys, 
            scorer=fuzz.token_set_ratio,
            limit=limit * 2  # 多取一些用于去重
        )
        
        for match_key, score, _ in fuzzy_results:
            if score >= self.threshold:
                item = self.search_index[match_key].copy()
                item["score"] = float(score)
                item["match_type"] = "fuzzy"
                item["match_key"] = match_key
                matches.append(item)
        
        return matches
    
    def _deduplicate_and_sort(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """去重并排序"""
        # 按item_id去重
        seen_items = {}
        for match in matches:
            item_id = match.get("item_id", "")
            if item_id:
                if item_id not in seen_items or match["score"] > seen_items[item_id]["score"]:
                    seen_items[item_id] = match
        
        # 按分数排序
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
        # 简单的关键词提取，可以后续优化
        keywords = []
        
        # 分割单词
        words = text.lower().split()
        keywords.extend(words)
        
        # 常见的菜品关键词
        food_keywords = [
            "pollo", "carne", "cerdo", "camarones", "arroz", "papa", 
            "tostones", "brocoli", "teriyaki", "agridulce", "plancha",
            "chicken", "beef", "pork", "shrimp", "rice", "potato"
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

# 全局别名匹配器实例
alias_matcher = AliasMatcher()
