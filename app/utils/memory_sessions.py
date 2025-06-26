"""
内存会话管理器 - 替代数据库存储
"""

import time
import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import json
import threading

from ..config import get_settings
from ..logger import get_logger

settings = get_settings()
logger = get_logger(__name__)

class ConversationState(Enum):
    """对话状态枚举"""
    GREETING = "greeting"
    ORDERING = "ordering"
    CLARIFYING = "clarifying"
    CONFIRMING_ORDER = "confirming_order"
    ASKING_NAME = "asking_name"
    COMPLETED = "completed"

@dataclass
class UserSession:
    """用户会话数据结构"""
    user_id: str
    state: ConversationState = ConversationState.GREETING
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    
    # 订单相关数据
    draft_lines: List[Dict[str, Any]] = field(default_factory=list)
    matched_items: List[Dict[str, Any]] = field(default_factory=list)
    pending_order: Optional[Dict[str, Any]] = None
    pending_choice: Optional[Dict[str, Any]] = None
    clarify_context: List[Dict[str, Any]] = field(default_factory=list)
    
    # 客户信息
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    
    # 订单历史
    last_order: Optional[Dict[str, Any]] = None
    order_count: int = 0
    
    # 会话统计
    message_count: int = 0
    voice_message_count: int = 0
    
    def update_activity(self):
        """更新最后活动时间"""
        self.last_activity = time.time()
        self.message_count += 1
    
    def is_expired(self, timeout_seconds: int = 3600) -> bool:
        """检查会话是否过期"""
        return (time.time() - self.last_activity) > timeout_seconds
    
    def reset_order_data(self):
        """重置订单相关数据"""
        self.draft_lines = []
        self.matched_items = []
        self.pending_order = None
        self.pending_choice = None
        self.clarify_context = []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于日志记录）"""
        return {
            "user_id": self.user_id,
            "state": self.state.value,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "customer_name": self.customer_name,
            "message_count": self.message_count,
            "order_count": self.order_count
        }

class MemorySessionManager:
    """内存会话管理器"""
    
    def __init__(self):
        self.sessions: Dict[str, UserSession] = {}
        self._lock = threading.Lock()
        self.cleanup_task = None
        self.max_sessions = settings.max_sessions_in_memory
        self.timeout_seconds = settings.session_timeout_seconds
        
        # 启动清理任务
        self._start_cleanup_task()
    
    def _start_cleanup_task(self):
        """启动定期清理任务"""
        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(settings.session_cleanup_interval)
                    self.cleanup_expired_sessions()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in cleanup task: {e}")
        
        self.cleanup_task = asyncio.create_task(cleanup_loop())
    
    def get_session(self, user_id: str) -> UserSession:
        """获取或创建用户会话"""
        with self._lock:
            if user_id not in self.sessions:
                # 检查会话数量限制
                if len(self.sessions) >= self.max_sessions:
                    self._evict_oldest_session()
                
                self.sessions[user_id] = UserSession(user_id=user_id)
                logger.info(f"Created new session for user {user_id}")
            
            session = self.sessions[user_id]
            session.update_activity()
            return session
    
    def update_session(self, user_id: str, **updates) -> UserSession:
        """更新会话数据"""
        session = self.get_session(user_id)
        
        with self._lock:
            for key, value in updates.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            
            session.update_activity()
        
        return session
    
    def delete_session(self, user_id: str) -> bool:
        """删除会话"""
        with self._lock:
            if user_id in self.sessions:
                del self.sessions[user_id]
                logger.info(f"Deleted session for user {user_id}")
                return True
            return False
    
    def cleanup_expired_sessions(self) -> int:
        """清理过期会话"""
        with self._lock:
            expired_users = []
            
            for user_id, session in self.sessions.items():
                if session.is_expired(self.timeout_seconds):
                    expired_users.append(user_id)
            
            for user_id in expired_users:
                del self.sessions[user_id]
            
            if expired_users:
                logger.info(f"Cleaned up {len(expired_users)} expired sessions")
            
            return len(expired_users)
    
    def _evict_oldest_session(self):
        """驱逐最老的会话"""
        if not self.sessions:
            return
        
        oldest_user = min(
            self.sessions.keys(),
            key=lambda uid: self.sessions[uid].last_activity
        )
        
        del self.sessions[oldest_user]
        logger.info(f"Evicted oldest session for user {oldest_user}")
    
    def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计信息"""
        with self._lock:
            total_sessions = len(self.sessions)
            
            if total_sessions == 0:
                return {
                    "total_sessions": 0,
                    "active_sessions": 0,
                    "avg_age_minutes": 0,
                    "states": {}
                }
            
            current_time = time.time()
            active_sessions = 0
            total_age = 0
            states = {}
            
            for session in self.sessions.values():
                # 活跃会话（最近5分钟有活动）
                if (current_time - session.last_activity) < 300:
                    active_sessions += 1
                
                # 计算平均年龄
                total_age += (current_time - session.created_at)
                
                # 统计状态分布
                state = session.state.value
                states[state] = states.get(state, 0) + 1
            
            return {
                "total_sessions": total_sessions,
                "active_sessions": active_sessions,
                "avg_age_minutes": (total_age / total_sessions) / 60,
                "states": states,
                "memory_usage_mb": self._estimate_memory_usage()
            }
    
    def _estimate_memory_usage(self) -> float:
        """估算内存使用量（MB）"""
        try:
            # 简单估算：每个会话大约1-2KB
            session_count = len(self.sessions)
            estimated_kb = session_count * 1.5
            return round(estimated_kb / 1024, 2)
        except:
            return 0.0
    
    def export_sessions(self) -> List[Dict[str, Any]]:
        """导出会话数据（用于调试）"""
        with self._lock:
            return [session.to_dict() for session in self.sessions.values()]
    
    def clear_all_sessions(self) -> int:
        """清空所有会话（用于管理）"""
        with self._lock:
            count = len(self.sessions)
            self.sessions.clear()
            logger.info(f"Cleared all {count} sessions")
            return count
    
    def shutdown(self):
        """关闭会话管理器"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
        
        with self._lock:
            session_count = len(self.sessions)
            self.sessions.clear()
        
        logger.info(f"Session manager shutdown, cleared {session_count} sessions")

# 全局会话管理器实例
session_manager = MemorySessionManager()

# 便捷函数
def get_user_session(user_id: str) -> UserSession:
    """获取用户会话"""
    return session_manager.get_session(user_id)

def update_user_session(user_id: str, **updates) -> UserSession:
    """更新用户会话"""
    return session_manager.update_session(user_id, **updates)

def delete_user_session(user_id: str) -> bool:
    """删除用户会话"""
    return session_manager.delete_session(user_id)

def get_session_statistics() -> Dict[str, Any]:
    """获取会话统计"""
    return session_manager.get_session_stats()
