"""WhatsApp 消息处理模块"""
import asyncio
from typing import Optional, Dict, Any
from fastapi import Request
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse
from utils.logger import get_logger
from utils.session_store import get_session, reset_session
from loyverse_api import create_customer, create_order
from gpt_tools import tool_parse_order, tool_get_menu
import json

logger = get_logger(__name__)

# 全局计数器，用于定期清理内存
_request_counter = 0
_CLEANUP_INTERVAL = 100

# ---------------- Conversation flow -----------------
TERMINATION_KEYWORDS = {"no", "nada", "eso es todo", "listo", "ya"}

def _is_finish_msg(text: str) -> bool:
    t = text.lower().strip()
    return any(t.startswith(k) or t == k for k in TERMINATION_KEYWORDS)


def _items_to_text(items):
    lines = []
    for it in items:
        lines.append(f"- {it['name']} x{it.get('quantity', 1)}")
    return "\n".join(lines)


async def _process_business_logic(user_id: str, user_message: str) -> str:
    """核心对话流程，基于 session_store 阶段机"""
    sess = get_session(user_id)
    stage = sess["stage"]

    # Stage 1: Greeting
    if stage == "GREETING":
        sess["stage"] = "CAPTURE"
        return "Hola, restaurante KongFood. ¿Qué desea ordenar hoy?"

    # Stage 2: Capture dishes loop
    if stage == "CAPTURE":
        if _is_finish_msg(user_message):
            if not sess["items"]:
                return "Aún no tengo ningún plato registrado. ¿Podría indicarme qué desea?"
            sess["stage"] = "NAME"
            return "Para finalizar, ¿podría indicarme su nombre, por favor?"

        # call parse_order
        order_json = tool_parse_order(user_message)
        try:
            data = json.loads(order_json)
        except Exception:
            data = {}
        items = data.get("items", []) if isinstance(data, dict) else []
        if not items:
            return "Disculpe, ¿podría aclararlo, por favor?"
        sess["items"].extend(items)
        first_item = items[0]
        return f"Perfecto, {first_item['name']} x{first_item.get('quantity',1)}. ¿Algo más?"

    # Stage 3: NAME
    if stage == "NAME":
        name = user_message.strip().title()
        sess["name"] = name
        customer_id = await create_customer(name=name, phone=user_id)
        sess["customer_id"] = customer_id
        sess["stage"] = "CONFIRM"
        # proceed to confirm immediately

    if stage == "CONFIRM":
        # build order_data
        order_data = {
            "items": sess["items"],
            "note": "Pedido vía WhatsApp bot"
        }
        result = await create_order(order_data)
        total = result.get("total_money_amount") if isinstance(result, dict) else None
        mains = [it for it in sess["items"] if it["name"].split()[0].lower() not in {"acompanantes", "aparte", "extra", "salsa", "no", "poco"}]
        mins = 15 if len(mains) >= 3 else 10
        lista = _items_to_text(sess["items"])
        sess["stage"] = "DONE"
        return (
            f"Gracias, {sess['name']}. Confirmo:\n{lista}\n"
            f"Total con impuesto: ${total if total else 'N/A'}.\n"
            f"Su orden estará lista en {mins} minutos. ¡Muchas gracias!"
        )

    # DONE or fallback
    reset_session(user_id)
    return "¡Muchas gracias! Si desea hacer otra orden, dígame por favor."


def _extract_user_id(form_data: Dict[str, Any]) -> str:
    """从 Twilio 表单数据中提取用户标识
    
    Args:
        form_data: Twilio webhook 表单数据
        
    Returns:
        用户唯一标识符
    """
    # 优先使用 WhatsApp 号码作为用户ID
    from_number = form_data.get("From", "")
    if from_number:
        # 清理号码格式，移除 whatsapp: 前缀
        user_id = from_number.replace("whatsapp:", "").replace("+", "").strip()
        if user_id:
            return user_id
    
    # 备用方案：使用 Twilio 账户信息
    account_sid = form_data.get("AccountSid", "")
    if account_sid:
        return f"account_{account_sid}"
    
    # 最后备用方案
    return "default_user"


def _create_error_response(error_message: str = None) -> Response:
    """创建错误响应的统一方法
    
    Args:
        error_message: 可选的错误消息，用于日志记录
        
    Returns:
        包含道歉消息的 TwiML 响应
    """
    if error_message:
        logger.error("创建错误响应: %s", error_message)
    
    # 多语言道歉消息
    apology_messages = [
        "Lo siento, se produjo un error al procesar su solicitud. Por favor, inténtelo de nuevo más tarde.",
        "Sorry, there was an error processing your request. Please try again later.",
        "抱歉，处理您的请求时出现错误。请稍后再试。"
    ]
    
    twiml_response = MessagingResponse()
    for message in apology_messages:
        twiml_response.message(message)
    
    return Response(content=str(twiml_response), media_type="application/xml")


async def handle_whatsapp_message(request: Request) -> Response:
    """处理来自 Twilio WhatsApp 的 webhook 请求
    
    这个函数设计为高度容错的：任何意外异常都会被捕获并转换为
    友好的道歉消息，确保客户体验不受影响。
    
    Args:
        request: FastAPI 请求对象
        
    Returns:
        包含回复消息的 TwiML XML 响应
    """
    global _request_counter
    
    try:
        # 解析请求表单数据
        try:
            form_data = await request.form()
            form_dict = dict(form_data)
        except Exception as e:
            logger.error("解析请求表单失败: %s", e)
            return _create_error_response("表单解析失败")
        
        # 提取用户消息
        user_message = form_dict.get("Body", "").strip()
        if not user_message:
            logger.warning("收到空的 WhatsApp 消息")
            user_message = "[空消息]"
        
        # 提取用户ID用于会话管理
        user_id = _extract_user_id(form_dict)
        
        # 记录请求信息
        logger.info("用户 %s 发送消息: %s", user_id, user_message[:100])
        
        # 获取用户专属的 Agent 并处理消息
        try:
            reply = await _process_business_logic(user_id, user_message)
        except Exception as e:
            logger.error("业务流程处理失败 (用户: %s): %s", user_id, e, exc_info=True)
            reply = "Lo siento, hubo un error al procesar su pedido. Por favor, inténtelo de nuevo más tarde."
        
        # 定期清理内存
        _request_counter += 1

        # 创建 TwiML 响应
        twiml_response = MessagingResponse()
        twiml_response.message(reply)
        
        return Response(content=str(twiml_response), media_type="application/xml")
        
    except Exception as e:
        # 最后的安全网：捕获所有未处理的异常
        logger.exception("处理 WhatsApp 消息时发生意外错误")
        return _create_error_response(f"意外错误: {e}")


async def handle_whatsapp_status(request: Request) -> Response:
    """处理 WhatsApp 消息状态更新（可选功能）
    
    Args:
        request: FastAPI 请求对象
        
    Returns:
        简单的确认响应
    """
    try:
        form_data = await request.form()
        message_status = form_data.get("MessageStatus", "")
        message_sid = form_data.get("MessageSid", "")
        
        logger.debug("消息状态更新: %s (SID: %s)", message_status, message_sid)
        
        # 这里可以添加状态处理逻辑，比如更新数据库等
        
        return Response(content="OK", media_type="text/plain")
        
    except Exception as e:
        logger.warning("处理消息状态更新失败: %s", e)
        return Response(content="OK", media_type="text/plain")  # 即使失败也返回 OK


def validate_twilio_webhook(request: Request, twilio_auth_token: str = None) -> bool:
    """验证 Twilio webhook 请求的真实性（可选安全功能）
    
    Args:
        request: FastAPI 请求对象
        twilio_auth_token: Twilio 认证令牌
        
    Returns:
        是否为有效的 Twilio 请求
    """
    # 这里可以实现 Twilio webhook 签名验证
    # 参考: https://www.twilio.com/docs/usage/webhooks/webhooks-security
    
    if not twilio_auth_token:
        logger.warning("未配置 Twilio 认证令牌，跳过 webhook 验证")
        return True
    
    # TODO: 实现完整的签名验证逻辑
    return True
