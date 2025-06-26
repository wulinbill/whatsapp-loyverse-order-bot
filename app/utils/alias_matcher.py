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
    """基于RapidFuzz的菜单项匹配器 - 按照最新流程要求"""
    
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
        查找匹配的菜单项 - 按照最新流程要求
        使用 token_set_ratio ≥ 80 作为成功标准
        
        Args:
            query: 查询字符串
            user_id: 用户ID
            limit: 返回结果数量限制
            
        Returns:
            匹配的菜单项列表，如果没有达到80分的匹配则返回空列表
        """
        start_time = time.time()
        
        try:
            query_lower = query.lower().strip()
            
            if not query_lower:
                return []
            
            # 按照新流程：使用token_set_ratio ≥ 80进行匹配
            matches = []
            
            # 1. 首先尝试精确匹配（100分）
            exact_matches = self._find_exact_matches(query_lower)
            matches.extend(exact_matches)
            
            # 2. 然后进行token_set_ratio模糊匹配（≥80分）
            if len(matches) < limit:
                fuzzy_matches = self._find_token_set_ratio_matches(query_lower, limit - len(matches))
                matches.extend(fuzzy_matches)
            
            # 3. 去重并排序
            matches = self._deduplicate_and_sort(matches)[:limit]
            
            # 4. 按照新流程要求：只返回≥80分的匹配
            high_quality_matches = [m for m in matches if m.get("score", 0) >= self.token_set_ratio_threshold]
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 记录匹配日志
            business_logger.log_menu_match(
                user_id=user_id,
                query=query,
                matches=high_quality_matches,
                method="rapidfuzz_token_set_ratio",
                duration_ms=duration_ms
            )
            
            # 记录匹配成功/失败
            if high_quality_matches:
                logger.info(f"RapidFuzz SUCCESS for '{query}': found {len(high_quality_matches)} matches ≥80")
            else:
                logger.info(f"RapidFuzz FAILED for '{query}': no matches ≥80 (will fallback to Claude)")
            
            return high_quality_matches
            
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
