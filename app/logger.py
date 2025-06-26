import logging
import sys
import json
import time
from datetime import datetime
from typing import Any, Dict, Optional
from .config import get_settings

settings = get_settings()

class JSONFormatter(logging.Formatter):
    """自定义JSON格式化器，便于日志分析"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # 添加额外的字段
        if hasattr(record, "stage"):
            log_data["stage"] = record.stage
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "order_id"):
            log_data["order_id"] = record.order_id
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        if hasattr(record, "error_code"):
            log_data["error_code"] = record.error_code
        if hasattr(record, "data"):
            log_data["data"] = record.data
            
        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_data, ensure_ascii=False)

def get_logger(name: str) -> logging.Logger:
    """获取配置好的logger实例"""
    logger = logging.getLogger(name)
    
    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    # 创建handler
    handler = logging.StreamHandler(sys.stdout)
    
    # 根据环境选择formatter
    if settings.environment == "production":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            fmt='%(asctime)s %(levelname)s %(name)s %(message)s',
            datefmt='%Y-%m-%dT%H:%M:%S'
        )
    
    handler.setFormatter(formatter)
    
    # 设置日志级别
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(log_level)
    handler.setLevel(log_level)
    
    logger.addHandler(handler)
    
    # 避免重复日志
    logger.propagate = False
    
    return logger

class LogStages:
    """日志阶段常量"""
    INBOUND = "inbound"
    LLM = "llm"
    MATCH = "match"
    POS = "pos"
    OUTBOUND = "outbound"
    AUTH = "auth"
    ERROR = "error"
    CUSTOMER = "customer"
    TRANSACTION = "transaction"

class BusinessLogger:
    """业务日志记录器，包含结构化日志方法"""
    
    def __init__(self, logger_name: str):
        self.logger = get_logger(logger_name)
    
    def log_inbound_message(self, user_id: str, message_type: str, content: str, metadata: Optional[Dict] = None):
        """记录入站消息"""
        self.logger.info(
            f"Incoming {message_type} message from {user_id}",
            extra={
                "stage": LogStages.INBOUND,
                "user_id": user_id,
                "data": {
                    "message_type": message_type,
                    "content": content[:200] + "..." if len(content) > 200 else content,
                    "metadata": metadata or {}
                }
            }
        )
    
    def log_llm_request(self, user_id: str, prompt_tokens: int, model: str, duration_ms: int):
        """记录LLM请求"""
        self.logger.info(
            f"LLM request completed for {user_id}",
            extra={
                "stage": LogStages.LLM,
                "user_id": user_id,
                "duration_ms": duration_ms,
                "data": {
                    "model": model,
                    "prompt_tokens": prompt_tokens
                }
            }
        )
    
    def log_menu_match(self, user_id: str, query: str, matches: list, method: str, duration_ms: int):
        """记录菜单匹配"""
        self.logger.info(
            f"Menu matching completed for {user_id}: {len(matches)} matches found",
            extra={
                "stage": LogStages.MATCH,
                "user_id": user_id,
                "duration_ms": duration_ms,
                "data": {
                    "query": query,
                    "method": method,
                    "match_count": len(matches),
                    "matches": [{"name": m.get("item_name", ""), "score": m.get("score", 0)} for m in matches[:3]]
                }
            }
        )
    
    def log_pos_order(self, user_id: str, order_id: str, total_amount: float, items_count: int, duration_ms: int):
        """记录POS订单"""
        self.logger.info(
            f"POS order created: {order_id}",
            extra={
                "stage": LogStages.POS,
                "user_id": user_id,
                "order_id": order_id,
                "duration_ms": duration_ms,
                "data": {
                    "total_amount": total_amount,
                    "items_count": items_count
                }
            }
        )
    
    def log_outbound_message(self, user_id: str, provider: str, message_type: str, success: bool, duration_ms: int):
        """记录出站消息"""
        status = "sent" if success else "failed"
        self.logger.info(
            f"Outbound message {status} to {user_id} via {provider}",
            extra={
                "stage": LogStages.OUTBOUND,
                "user_id": user_id,
                "duration_ms": duration_ms,
                "data": {
                    "provider": provider,
                    "message_type": message_type,
                    "success": success
                }
            }
        )
    
    def log_auth_token_refresh(self, service: str, success: bool, duration_ms: int, error_msg: Optional[str] = None):
        """记录认证token刷新"""
        status = "success" if success else "failed"
        self.logger.info(
            f"Token refresh {status} for {service}",
            extra={
                "stage": LogStages.AUTH,
                "duration_ms": duration_ms,
                "data": {
                    "service": service,
                    "success": success,
                    "error_message": error_msg
                }
            }
        )
    
    def log_error(self, user_id: str, stage: str, error_code: str, error_msg: str, exception: Optional[Exception] = None):
        """记录错误"""
        self.logger.error(
            f"Error in {stage}: {error_msg}",
            extra={
                "stage": LogStages.ERROR,
                "user_id": user_id,
                "error_code": error_code,
                "data": {
                    "original_stage": stage,
                    "error_message": error_msg
                }
            },
            exc_info=exception
        )
    
    # ========================================================================
    # 新增的缺失方法
    # ========================================================================
    
    def log_customer_activity(self, user_id: str, customer_id: str, activity_type: str, details: Optional[Dict[str, Any]] = None):
        """记录客户活动"""
        self.logger.info(
            f"Customer {activity_type}: {customer_id} for user {user_id}",
            extra={
                "stage": LogStages.CUSTOMER,
                "user_id": user_id,
                "data": {
                    "customer_id": customer_id,
                    "activity_type": activity_type,
                    "details": details or {}
                }
            }
        )
    
    def log_pos_transaction(self, user_id: str, receipt_id: str, total_amount: float, transaction_type: str = "sale", metadata: Optional[Dict[str, Any]] = None):
        """记录POS交易"""
        self.logger.info(
            f"POS {transaction_type}: Receipt {receipt_id} for ${total_amount:.2f} (User: {user_id})",
            extra={
                "stage": LogStages.TRANSACTION,
                "user_id": user_id,
                "order_id": receipt_id,
                "data": {
                    "receipt_id": receipt_id,
                    "total_amount": total_amount,
                    "transaction_type": transaction_type,
                    "metadata": metadata or {}
                }
            }
        )
    
    # ========================================================================
    # 其他有用的日志方法
    # ========================================================================
    
    def log_ai_interaction(self, user_id: str, interaction_type: str, input_text: str, output_text: str, metadata: Optional[Dict[str, Any]] = None):
        """记录AI交互"""
        input_preview = input_text[:50] + "..." if len(input_text) > 50 else input_text
        output_preview = output_text[:50] + "..." if len(output_text) > 50 else output_text
        
        self.logger.info(
            f"AI {interaction_type} for user {user_id}",
            extra={
                "stage": LogStages.LLM,
                "user_id": user_id,
                "data": {
                    "interaction_type": interaction_type,
                    "input_preview": input_preview,
                    "output_preview": output_preview,
                    "metadata": metadata or {}
                }
            }
        )
    
    def log_speech_processing(self, user_id: str, duration_seconds: float, success: bool, transcript: Optional[str] = None, error: Optional[str] = None):
        """记录语音处理"""
        status = "success" if success else "failed"
        
        data = {
            "duration_seconds": duration_seconds,
            "success": success
        }
        
        if transcript:
            preview = transcript[:50] + "..." if len(transcript) > 50 else transcript
            data["transcript_preview"] = preview
        
        if error:
            data["error"] = error
        
        self.logger.info(
            f"Speech processing {status} for user {user_id} ({duration_seconds:.1f}s)",
            extra={
                "stage": "speech",
                "user_id": user_id,
                "duration_ms": int(duration_seconds * 1000),
                "data": data
            }
        )
    
    def log_session_event(self, user_id: str, event_type: str, details: Optional[Dict[str, Any]] = None):
        """记录会话事件"""
        self.logger.info(
            f"Session {event_type} for user {user_id}",
            extra={
                "stage": "session",
                "user_id": user_id,
                "data": {
                    "event_type": event_type,
                    "details": details or {}
                }
            }
        )
    
    def log_webhook_event(self, provider: str, event_type: str, success: bool, metadata: Optional[Dict[str, Any]] = None):
        """记录webhook事件"""
        status = "processed" if success else "failed"
        
        self.logger.info(
            f"Webhook {event_type} from {provider} {status}",
            extra={
                "stage": "webhook",
                "data": {
                    "provider": provider,
                    "event_type": event_type,
                    "success": success,
                    "metadata": metadata or {}
                }
            }
        )

# 全局业务日志记录器实例
business_logger = BusinessLogger("whatsapp_bot.business")
