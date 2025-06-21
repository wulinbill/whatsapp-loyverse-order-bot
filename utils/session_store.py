"""改进的会话存储模块 - 线程安全版本"""
from __future__ import annotations
import time
import threading
from typing import Dict, Any
from utils.logger import get_logger

logger = get_logger(__name__)

# 线程安全的会话存储
_SESSIONS: Dict[str, Dict[str, Any]] = {}
_lock = threading.RLock()
TTL = 60 * 60  # 1 hour

# 清理计数器
_cleanup_counter = 0
CLEANUP_INTERVAL = 50  # 每50次操作清理一次过期会话


def get_session(user_id: str) -> Dict[str, Any]:
    """获取用户会话，线程安全"""
    with _lock:
        sess = _SESSIONS.get(user_id)
        now = time.time()
        
        # 检查会话是否过期
        if sess and now - sess.get("_ts", now) > TTL:
            logger.debug("会话已过期，删除用户 %s 的会话", user_id)
            del _SESSIONS[user_id]
            sess = None
        
        # 创建新会话
        if not sess:
            sess = {
                "stage": "GREETING",
                "items": [],
                "customer_id": None,
                "name": None,
                "_ts": now,
                "_created": now,
            }
            _SESSIONS[user_id] = sess
            logger.debug("为用户 %s 创建新会话", user_id)
        else:
            # 刷新时间戳
            sess["_ts"] = now
        
        # 定期清理过期会话
        _trigger_cleanup()
        
        return sess


def reset_session(user_id: str) -> bool:
    """重置用户会话，线程安全"""
    with _lock:
        if user_id in _SESSIONS:
            del _SESSIONS[user_id]
            logger.debug("重置用户 %s 的会话", user_id)
            return True
        return False


def update_session(user_id: str, updates: Dict[str, Any]) -> None:
    """更新会话数据，线程安全"""
    with _lock:
        if user_id in _SESSIONS:
            _SESSIONS[user_id].update(updates)
            _SESSIONS[user_id]["_ts"] = time.time()
            logger.debug("更新用户 %s 的会话数据: %s", user_id, list(updates.keys()))


def get_session_stats() -> Dict[str, Any]:
    """获取会话统计信息"""
    with _lock:
        now = time.time()
        active_sessions = 0
        expired_sessions = 0
        
        for sess in _SESSIONS.values():
            if now - sess.get("_ts", now) > TTL:
                expired_sessions += 1
            else:
                active_sessions += 1
        
        return {
            "total_sessions": len(_SESSIONS),
            "active_sessions": active_sessions,
            "expired_sessions": expired_sessions,
            "ttl_seconds": TTL
        }


def _trigger_cleanup() -> None:
    """定期触发清理过期会话"""
    global _cleanup_counter
    _cleanup_counter += 1
    
    if _cleanup_counter >= CLEANUP_INTERVAL:
        _cleanup_counter = 0
        cleanup_expired_sessions()


def cleanup_expired_sessions() -> int:
    """清理过期会话，返回清理的数量"""
    with _lock:
        now = time.time()
        expired_users = []
        
        for user_id, sess in _SESSIONS.items():
            if now - sess.get("_ts", now) > TTL:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            del _SESSIONS[user_id]
        
        if expired_users:
            logger.info("清理了 %d 个过期会话", len(expired_users))
        
        return len(expired_users)


def cleanup_all_sessions() -> int:
    """清理所有会话（用于维护）"""
    with _lock:
        count = len(_SESSIONS)
        _SESSIONS.clear()
        logger.info("清理了所有 %d 个会话", count)
        return count
