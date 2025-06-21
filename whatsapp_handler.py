"""修复后的 WhatsApp 消息处理模块"""
import json
from typing import Dict, Any
from fastapi import Request
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse

from config import settings, constants
from utils.logger import get_logger
from utils.session_store import get_session, reset_session, update_session, cleanup_expired_sessions
from utils.validators import (
    validate_user_message, validate_user_id, validate_customer_name,
    validate_twilio_form_data, ValidationError, sanitize_for_logging
)
from loyverse_api import create_customer, create_ticket
from gpt_tools import tool_parse_order

logger = get_logger(__name__)

# 全局计数器，用于定期清理
_request_counter = 0


def _is_finish_msg(text: str) -> bool:
    """检查是否为结束消息"""
    if not text:
        return False
    
    text_lower = text.lower().strip()
    return any(
        text_lower.startswith(keyword) or text_lower == keyword 
        for keyword in constants.TERMINATION_KEYWORDS
    )


def _items_to_text(items: list) -> str:
    """将订单项目转换为文本格式"""
    if not items:
        return "无项目"
    
    lines = []
    for item in items:
        name = item.get('name', '未知商品')
        quantity = item.get('quantity', 1)
        lines.append(f"- {name} x{quantity}")
    
    return "\n".join(lines)


def _calculate_prep_time(items: list) -> int:
    """计算准备时间"""
    if not items:
        return settings.default_prep_time_minutes
    
    # 计算主菜数量（排除配菜和额外项目）
    main_items = [
        item for item in items 
        if not any(keyword in item.get('name', '').lower() 
                  for keyword in ['acompañantes', 'aparte', 'extra', 'salsa', 'sin', 'poco'])
    ]
    
    if len(main_items) >= settings.large_order_threshold:
        return settings.large_order_prep_time_minutes
    else:
        return settings.default_prep_time_minutes


async def _process_business_logic(user_id: str, user_message: str) -> str:
    """核心业务逻辑处理 - 基于状态机的对话流程"""
    try:
        sess = get_session(user_id)
        stage = sess["stage"]
        
        logger.debug("用户 %s 当前阶段: %s", user_id, stage)
        
        # Stage 1: 初始问候
        if stage == constants.ORDER_STAGE_GREETING:
            update_session(user_id, {"stage": constants.ORDER_STAGE_CAPTURE})
            return constants.GREETING_MESSAGE
        
        # Stage 2: 收集菜品循环
        elif stage == constants.ORDER_STAGE_CAPTURE:
            if _is_finish_msg(user_message):
                if not sess.get("items"):
                    return constants.EMPTY_ORDER_MESSAGE
                
                update_session(user_id, {"stage": constants.ORDER_STAGE_NAME})
                return constants.NAME_REQUEST_MESSAGE
            
            # 解析订单
            try:
                order_json = tool_parse_order(user_message)
                order_data = json.loads(order_json)
            except Exception as e:
                logger.warning("订单解析失败 (用户: %s): %s", user_id, str(e))
                return constants.CLARIFICATION_MESSAGE
            
            # 检查解析结果
            items = order_data.get("items", []) if isinstance(order_data, dict) else []
            if not items:
                return constants.CLARIFICATION_MESSAGE
            
            # 添加到会话
            current_items = sess.get("items", [])
            current_items.extend(items)
            update_session(user_id, {"items": current_items})
            
            # 确认添加的第一个项目
            first_item = items[0]
            item_name = first_item.get('name', '商品')
            quantity = first_item.get('quantity', 1)
            
            return f"Perfecto, {item_name} x{quantity}. ¿Algo más?"
        
        # Stage 3: 获取客户姓名
        elif stage == constants.ORDER_STAGE_NAME:
            try:
                clean_name = validate_customer_name(user_message)
            except ValidationError as e:
                logger.warning("姓名验证失败 (用户: %s): %s", user_id, e.message)
                return "Por favor, indique un nombre válido."
            
            # 创建客户记录
            try:
                customer_id = await create_customer(name=clean_name, phone=user_id)
                update_session(user_id, {
                    "name": clean_name,
                    "customer_id": customer_id,
                    "stage": constants.ORDER_STAGE_CONFIRM
                })
                logger.info("客户创建成功 (用户: %s, 姓名: %s)", user_id, clean_name)
            except Exception as e:
                logger.error("创建客户失败 (用户: %s): %s", user_id, str(e))
                # 即使客户创建失败，也继续流程
                update_session(user_id, {
                    "name": clean_name,
                    "customer_id": None,
                    "stage": constants.ORDER_STAGE_CONFIRM
                })
            
            # 立即进入确认阶段
            return await _process_confirm_stage(user_id, sess)
        
        # Stage 4: 确认订单
        elif stage == constants.ORDER_STAGE_CONFIRM:
            return await _process_confirm_stage(user_id, sess)
        
        # Stage 5: 完成或其他情况
        else:
            reset_session(user_id)
            return constants.THANK_YOU_MESSAGE
            
    except Exception as e:
        logger.error("业务逻辑处理异常 (用户: %s): %s", user_id, str(e))
        reset_session(user_id)
        return constants.ERROR_MESSAGES["es"]


async def _process_confirm_stage(user_id: str, sess: Dict[str, Any]) -> str:
    """处理订单确认阶段"""
    try:
        # 构建订单数据
        order_data = {
            "items": sess.get("items", []),
            "note": f"Pedido vía WhatsApp bot - Cliente: {sess.get('name', 'Desconocido')}"
        }
        
        # 提交到 POS 系统
        result = await create_ticket(order_data)
        
        # 计算准备时间
        prep_time = _calculate_prep_time(sess.get("items", []))
        
        # 获取总金额
        total_amount = result.get("total_money_amount") if isinstance(result, dict) else None
        
        # 生成订单摘要
        items_text = _items_to_text(sess.get("items", []))
        customer_name = sess.get("name", "Cliente")
        
        # 标记会话完成
        update_session(user_id, {"stage": constants.ORDER_STAGE_DONE})
        
        logger.info("订单提交成功 (用户: %s, 客户: %s)", user_id, customer_name)
        
        # 构建确认消息
        confirmation_msg = (
            f"Gracias, {customer_name}. Confirmo su pedido:\n\n"
            f"{items_text}\n\n"
        )
        
        if total_amount:
            confirmation_msg += f"Total con impuesto: ${total_amount:.2f}\n"
        
        confirmation_msg += (
            f"Su orden estará lista en {prep_time} minutos.\n"
            f"¡Muchas gracias por elegir KongFood!"
        )
        
        return confirmation_msg
        
    except Exception as e:
        logger.error("订单确认处理失败 (用户: %s): %s", user_id, str(e))
        reset_session(user_id)
        return "Lo siento, hubo un problema al procesar su pedido. Por favor, intente nuevamente."


def _extract_user_id(form_data: Dict[str, str]) -> str:
    """从 Twilio 表单数据中提取并验证用户ID"""
    from_number = form_data.get("from", "") or form_data.get("From", "")
    
    if from_number:
        # 清理号码格式
        clean_number = from_number.replace("whatsapp:", "").replace("+", "").strip()
        if clean_number:
            try:
                return validate_user_id(clean_number)
            except ValidationError:
                pass
    
    # 备用方案
    account_sid = form_data.get("AccountSid", "")
    if account_sid:
        return f"account_{account_sid[:10]}"
    
    return "default_user"


def _create_error_response(error_message: str = None, error_type: str = "general") -> Response:
    """创建错误响应"""
    if error_message:
        logger.error("创建错误响应 (%s): %s", error_type, error_message)
    
    # 根据错误类型选择合适的消息
    if error_type == "validation":
        message = "Por favor, envíe un mensaje válido."
    elif error_type == "timeout":
        message = "Su sesión ha expirado. Por favor, inicie una nueva conversación."
    else:
        message = constants.ERROR_MESSAGES["es"]
    
    twiml_response = MessagingResponse()
    twiml_response.message(message)
    
    return Response(content=str(twiml_response), media_type="application/xml")


async def handle_whatsapp_message(request: Request) -> Response:
    """处理 WhatsApp 消息的主入口点
    
    完全重写，移除了不必要的 LLM 二次调用，
    增强了错误处理和输入验证。
    """
    global _request_counter
    
    try:
        # 解析和验证请求数据
        try:
            form_data = await request.form()
            validated_data = validate_twilio_form_data(dict(form_data))
        except ValidationError as e:
            logger.warning("请求验证失败: %s", e.message)
            return _create_error_response(e.message, "validation")
        except Exception as e:
            logger.error("解析请求表单失败: %s", str(e))
            return _create_error_response("解析请求失败")
        
        # 提取并验证用户消息和ID
        user_message = validated_data.get("body", "").strip()
        user_id = _extract_user_id(validated_data)
        
        # 验证用户消息
        if not user_message:
            logger.warning("收到空消息 (用户: %s)", user_id)
            return _create_error_response("消息为空", "validation")
        
        try:
            clean_message = validate_user_message(user_message)
        except ValidationError as e:
            logger.warning("消息验证失败 (用户: %s): %s", user_id, e.message)
            return _create_error_response("消息格式无效", "validation")
        
        # 记录请求（使用清理后的数据）
        logger.info("用户 %s 发送消息: %s", 
                   user_id, sanitize_for_logging(clean_message))
        
        # 处理业务逻辑
        try:
            reply = await _process_business_logic(user_id, clean_message)
        except Exception as e:
            logger.error("业务逻辑处理失败 (用户: %s): %s", user_id, str(e))
            reset_session(user_id)  # 重置会话状态
            reply = constants.ERROR_MESSAGES["es"]
        
        # 定期清理过期会话
        _request_counter += 1
        if _request_counter >= settings.cleanup_interval:
            _request_counter = 0
            try:
                cleanup_expired_sessions()
            except Exception as e:
                logger.warning("清理会话失败: %s", str(e))
        
        # 创建响应
        twiml_response = MessagingResponse()
        twiml_response.message(reply)
        
        logger.debug("发送回复给用户 %s: %s", 
                    user_id, sanitize_for_logging(reply))
        
        return Response(content=str(twiml_response), media_type="application/xml")
        
    except Exception as e:
        # 最后的安全网
        logger.exception("处理 WhatsApp 消息时发生意外错误")
        return _create_error_response(f"系统错误: {str(e)}")


async def handle_whatsapp_status(request: Request) -> Response:
    """处理 WhatsApp 消息状态更新"""
    try:
        form_data = await request.form()
        message_status = form_data.get("MessageStatus", "")
        message_sid = form_data.get("MessageSid", "")
        
        logger.debug("消息状态更新: %s (SID: %s)", message_status, message_sid)
        
        # 这里可以添加状态处理逻辑
        # 例如：更新数据库中的消息状态
        
        return Response(content="OK", media_type="text/plain")
        
    except Exception as e:
        logger.warning("处理消息状态更新失败: %s", str(e))
        return Response(content="OK", media_type="text/plain")


def validate_twilio_webhook(request: Request, twilio_auth_token: str = None) -> bool:
    """验证 Twilio webhook 请求的真实性
    
    TODO: 实现完整的签名验证
    当前返回 True，在生产环境中应实现真实验证
    """
    if not settings.webhook_validation_enabled:
        return True
        
    if not twilio_auth_token:
        logger.warning("Webhook 验证已启用但未提供认证令牌")
        return True
    
    # TODO: 实现 Twilio 签名验证
    # 参考: https://www.twilio.com/docs/usage/webhooks/webhooks-security
    
    return True


# 添加一些实用工具函数

def get_session_info(user_id: str) -> Dict[str, Any]:
    """获取用户会话信息（用于调试）"""
    try:
        validated_user_id = validate_user_id(user_id)
        sess = get_session(validated_user_id)
        return {
            "user_id": validated_user_id,
            "stage": sess.get("stage"),
            "items_count": len(sess.get("items", [])),
            "customer_name": sess.get("name"),
            "has_customer_id": bool(sess.get("customer_id")),
            "created_time": sess.get("_created"),
            "last_activity": sess.get("_ts")
        }
    except Exception as e:
        logger.error("获取会话信息失败: %s", str(e))
        return {"error": str(e)}


def reset_user_session(user_id: str) -> bool:
    """重置用户会话（管理员功能）"""
    try:
        validated_user_id = validate_user_id(user_id)
        result = reset_session(validated_user_id)
        logger.info("管理员重置用户会话: %s", validated_user_id)
        return result
    except Exception as e:
        logger.error("重置用户会话失败: %s", str(e))
        return False
