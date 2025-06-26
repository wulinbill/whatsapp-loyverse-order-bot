import time
import asyncio
from typing import List, Dict, Any, Optional
# 移除直接导入
# import psycopg2
# import numpy as np
# from psycopg2.extras import RealDictCursor
import json

from ..config import get_settings
from ..logger import get_logger, business_logger

settings = get_settings()
logger = get_logger(__name__)

class VectorSearchClient:
    """基于OpenAI embeddings和PGVector的向量搜索客户端"""
    
    def __init__(self):
        # 条件导入和初始化 OpenAI 客户端
        self.openai_client = None
        self.psycopg2 = None
        self.numpy = None
        
        try:
            # 只有在配置了 API key 且启用了向量搜索时才导入 openai
            if settings.openai_api_key and settings.enable_vector_search:
                import openai
                self.openai_client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
                logger.info("OpenAI client initialized for vector search")
            else:
                logger.info("OpenAI client not initialized - API key missing or vector search disabled")
        except ImportError:
            logger.warning("OpenAI library not installed. Vector search will be disabled.")
            self.openai_client = None
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            self.openai_client = None
        
        # 条件导入 PostgreSQL 相关模块
        try:
            if settings.enable_vector_search:
                import psycopg2
                from psycopg2.extras import RealDictCursor
                import numpy as np
                
                self.psycopg2 = psycopg2
                self.RealDictCursor = RealDictCursor
                self.numpy = np
                logger.info("PostgreSQL libraries loaded for vector search")
            else:
                logger.info("PostgreSQL libraries not loaded - vector search disabled")
        except ImportError:
            logger.warning("PostgreSQL libraries (psycopg2) not installed. Vector search will be disabled.")
            self.psycopg2 = None
        except Exception as e:
            logger.error(f"Failed to load PostgreSQL libraries: {e}")
            self.psycopg2 = None
            
        self.embedding_model = getattr(settings, 'openai_embedding_model', 'text-embedding-3-small')
        self.threshold = getattr(settings, 'vector_search_threshold', 0.7)
        self._connection_pool = None
    
    async def _get_connection(self):
        """获取数据库连接"""
        # 检查是否有 psycopg2
        if not self.psycopg2:
            logger.debug("psycopg2 not available, cannot connect to PostgreSQL")
            return None
            
        # 检查是否配置了PostgreSQL
        postgres_config_attrs = ['postgres_password', 'postgres_host', 'postgres_port', 'postgres_db', 'postgres_user']
        
        # 如果没有这些配置，说明没有配置PostgreSQL
        if not all(hasattr(settings, attr) for attr in postgres_config_attrs):
            logger.debug("PostgreSQL not configured in settings")
            return None
            
        if not getattr(settings, 'postgres_password', None):
            logger.debug("PostgreSQL password not configured")
            return None
            
        try:
            connection = self.psycopg2.connect(
                host=settings.postgres_host,
                port=settings.postgres_port,
                database=settings.postgres_db,
                user=settings.postgres_user,
                password=settings.postgres_password
            )
            return connection
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            return None
    
    async def search_similar_items(self, query: str, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        使用向量搜索查找相似菜品
        
        Args:
            query: 查询字符串
            user_id: 用户ID
            limit: 返回结果数量限制
            
        Returns:
            相似菜品列表，包含相似度分数
        """
        start_time = time.time()
        
        try:
            # 检查是否启用向量搜索
            if not settings.enable_vector_search:
                logger.debug("Vector search is disabled in settings")
                return []
                
            if not self.openai_client:
                logger.debug("OpenAI client not available, skipping vector search")
                return []
                
            if not self.psycopg2:
                logger.debug("PostgreSQL not available, skipping vector search")
                return []
            
            # 1. 生成查询向量
            query_embedding = await self._get_embedding(query)
            if not query_embedding:
                return []
            
            # 2. 在数据库中搜索相似向量
            matches = await self._search_vectors(query_embedding, limit)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 记录搜索日志
            business_logger.log_menu_match(
                user_id=user_id,
                query=query,
                matches=matches,
                method="vector_search",
                duration_ms=duration_ms
            )
            
            return matches
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="match",
                error_code="VECTOR_SEARCH_FAILED",
                error_msg=str(e),
                exception=e
            )
            return []
    
    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """获取文本的embedding向量"""
        if not self.openai_client:
            return None
            
        try:
            response = await self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            
            if response.data and len(response.data) > 0:
                return response.data[0].embedding
            else:
                logger.error("Empty embedding response from OpenAI")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get embedding: {e}")
            return None
    
    async def _search_vectors(self, query_embedding: List[float], limit: int) -> List[Dict[str, Any]]:
        """在数据库中搜索相似向量"""
        connection = await self._get_connection()
        if not connection:
            return []
        
        try:
            with connection.cursor(cursor_factory=self.RealDictCursor) as cursor:
                # 使用余弦相似度搜索
                query = """
                SELECT 
                    item_id,
                    item_name,
                    category_name,
                    price,
                    sku,
                    aliases,
                    keywords,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM menu_embeddings 
                WHERE 1 - (embedding <=> %s::vector) > %s
                ORDER BY similarity DESC
                LIMIT %s;
                """
                
                # 将embedding转换为字符串格式
                embedding_str = f"[{','.join(map(str, query_embedding))}]"
                
                cursor.execute(query, (embedding_str, embedding_str, self.threshold, limit))
                results = cursor.fetchall()
                
                # 转换结果格式
                matches = []
                for row in results:
                    match = dict(row)
                    match["score"] = float(match["similarity"] * 100)  # 转换为百分制
                    match["match_type"] = "vector"
                    matches.append(match)
                
                return matches
                
        except Exception as e:
            logger.error(f"Vector search query failed: {e}")
            return []
        finally:
            connection.close()
    
    async def build_embeddings_index(self):
        """构建菜单项的embeddings索引"""
        if not self.openai_client:
            logger.warning("OpenAI client not configured, cannot build embeddings index")
            return
        
        if not self.psycopg2:
            logger.warning("PostgreSQL not available, cannot build embeddings index")
            return
        
        if not settings.enable_vector_search:
            logger.info("Vector search disabled, skipping embeddings index build")
            return
        
        logger.info("Building embeddings index...")
        
        try:
            # 1. 加载菜单数据
            menu_items = await self._load_menu_items()
            
            # 2. 创建数据库表
            await self._create_embeddings_table()
            
            # 3. 生成并存储embeddings
            for item in menu_items:
                await self._process_menu_item(item)
            
            logger.info(f"Successfully built embeddings index for {len(menu_items)} items")
            
        except Exception as e:
            logger.error(f"Failed to build embeddings index: {e}")
    
    async def _load_menu_items(self) -> List[Dict[str, Any]]:
        """加载菜单项数据"""
        try:
            import os
            
            current_dir = os.path.dirname(os.path.abspath(__file__))
            menu_file = os.path.join(current_dir, "..", "knowledge_base", "menu_kb.json")
            
            if not os.path.exists(menu_file):
                logger.warning(f"Menu file not found: {menu_file}")
                return []
            
            with open(menu_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            menu_items = []
            for category_name, category_data in data.get("menu_categories", {}).items():
                if isinstance(category_data, dict) and "items" in category_data:
                    for item in category_data["items"]:
                        menu_items.append(item)
            
            return menu_items
            
        except Exception as e:
            logger.error(f"Failed to load menu items: {e}")
            return []
    
    async def _create_embeddings_table(self):
        """创建embeddings表"""
        connection = await self._get_connection()
        if not connection:
            return
        
        try:
            with connection.cursor() as cursor:
                # 创建扩展
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                
                # 创建表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS menu_embeddings (
                        id SERIAL PRIMARY KEY,
                        item_id VARCHAR(255) UNIQUE NOT NULL,
                        item_name TEXT NOT NULL,
                        category_name VARCHAR(255),
                        price DECIMAL(10, 2),
                        sku VARCHAR(100),
                        aliases TEXT[],
                        keywords TEXT[],
                        embedding vector(1536),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # 创建索引
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS menu_embeddings_vector_idx 
                    ON menu_embeddings USING ivfflat (embedding vector_cosine_ops);
                """)
                
                connection.commit()
                
        except Exception as e:
            logger.error(f"Failed to create embeddings table: {e}")
            connection.rollback()
        finally:
            connection.close()
    
    async def _process_menu_item(self, item: Dict[str, Any]):
        """处理单个菜单项，生成并存储embedding"""
        try:
            # 构建用于embedding的文本
            text_parts = []
            
            # 添加菜品名称
            if item.get("item_name"):
                text_parts.append(item["item_name"])
            
            # 添加别名
            if item.get("aliases"):
                text_parts.extend(item["aliases"])
            
            # 添加关键词
            if item.get("keywords"):
                text_parts.extend(item["keywords"])
            
            # 添加分类名称
            if item.get("category_name"):
                text_parts.append(item["category_name"])
            
            embedding_text = " ".join(text_parts)
            
            # 生成embedding
            embedding = await self._get_embedding(embedding_text)
            if not embedding:
                logger.warning(f"Failed to generate embedding for item {item.get('item_id')}")
                return
            
            # 存储到数据库
            await self._store_embedding(item, embedding)
            
        except Exception as e:
            logger.error(f"Failed to process menu item {item.get('item_id')}: {e}")
    
    async def _store_embedding(self, item: Dict[str, Any], embedding: List[float]):
        """存储embedding到数据库"""
        connection = await self._get_connection()
        if not connection:
            return
        
        try:
            with connection.cursor() as cursor:
                embedding_str = f"[{','.join(map(str, embedding))}]"
                
                cursor.execute("""
                    INSERT INTO menu_embeddings 
                    (item_id, item_name, category_name, price, sku, aliases, keywords, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (item_id) DO UPDATE SET
                        item_name = EXCLUDED.item_name,
                        category_name = EXCLUDED.category_name,
                        price = EXCLUDED.price,
                        sku = EXCLUDED.sku,
                        aliases = EXCLUDED.aliases,
                        keywords = EXCLUDED.keywords,
                        embedding = EXCLUDED.embedding,
                        updated_at = CURRENT_TIMESTAMP;
                """, (
                    item.get("item_id"),
                    item.get("item_name"),
                    item.get("category_name"),
                    item.get("price"),
                    item.get("sku"),
                    item.get("aliases", []),
                    item.get("keywords", []),
                    embedding_str
                ))
                
                connection.commit()
                
        except Exception as e:
            logger.error(f"Failed to store embedding: {e}")
            connection.rollback()
        finally:
            connection.close()

# 全局向量搜索客户端实例
vector_search_client = VectorSearchClient()
