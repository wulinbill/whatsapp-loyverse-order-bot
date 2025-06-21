"""输入验证模块"""
import re
import html
from typing import Dict, Any, Optional
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# 危险字符模式
DANGEROUS_PATTERNS = [
    r'<script[^>]*>.*?</script>',  # Script 标签
    r'javascript:',               # JavaScript 协议
    r'on\w+\s*=',                # 事件处理器
    r'<iframe[^>]*>.*?</iframe>', # iframe 标签
]

# 编译正则表达式以提高性能
DANGEROUS_REGEX = [re.compile(pattern, re.IGNORECASE | re.DOTALL) for pattern in DANGEROUS_PATTERNS]


class ValidationError(Exception):
    """验证错误异常"""
    def __init__(self, message: str, error_code: str = None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


def validate_user_message(message: str) -> str:
    """验证和清理用户消息
    
    Args:
        message: 原始用户消息
        
    Returns:
        清理后的安全消息
        
    Raises:
        ValidationError: 消息验证失败
    """
    if not message:
        raise ValidationError("消息不能为空", "EMPTY_MESSAGE")
    
    # 检查消息长度
    if len(message) > settings.max_message_length:
        raise ValidationError(
            f"消息过长，最大长度为 {settings.max_message_length} 字符",
            "MESSAGE_TOO_LONG"
        )
    
    # 检查是否包含危险内容
    for pattern in DANGEROUS_REGEX:
        if pattern.search(message):
            logger.warning("检测到潜在危险内容: %s", message[:100])
            raise ValidationError("消息包含不安全内容", "UNSAFE_CONTENT")
    
    # HTML 实体编码防止 XSS
    clean_message = html.escape(message, quote=True)
    
    # 移除多余的空白字符
    clean_message = re.sub(r'\s+', ' ', clean_message).strip()
    
    # 基本长度检查（清理后）
    if len(clean_message) == 0:
        raise ValidationError("消息清理后为空", "EMPTY_AFTER_CLEANING")
    
    return clean_message


def validate_user_id(user_id: str) -> str:
    """验证用户ID
    
    Args:
        user_id: 原始用户ID
        
    Returns:
        清理后的用户ID
        
    Raises:
        ValidationError: 用户ID验证失败
    """
    if not user_id:
        raise ValidationError("用户ID不能为空", "EMPTY_USER_ID")
    
    # 移除潜在的危险字符
    clean_user_id = re.sub(r'[<>"\'\s]', '', user_id)
    
    # 长度检查
    if len(clean_user_id) > 50:
        raise ValidationError("用户ID过长", "USER_ID_TOO_LONG")
    
    if len(clean_user_id) == 0:
        raise ValidationError("用户ID清理后为空", "USER_ID_EMPTY_AFTER_CLEANING")
    
    return clean_user_id


def validate_customer_name(name: str) -> str:
    """验证客户姓名
    
    Args:
        name: 原始姓名
        
    Returns:
        清理后的姓名
        
    Raises:
        ValidationError: 姓名验证失败
    """
    if not name:
        raise ValidationError("姓名不能为空", "EMPTY_NAME")
    
    # 移除潜在的危险字符，但保留基本标点
    clean_name = re.sub(r'[<>"\']', '', name.strip())
    
    # 长度检查
    if len(clean_name) > 100:
        raise ValidationError("姓名过长", "NAME_TOO_LONG")
    
    if len(clean_name) == 0:
        raise ValidationError("姓名清理后为空", "NAME_EMPTY_AFTER_CLEANING")
    
    # 基本格式检查（只允许字母、数字、空格和基本标点）
    if not re.match(r'^[a-zA-Z0-9\u00C0-\u017F\u4e00-\u9fff\s\.\-_]+$', clean_name):
        raise ValidationError("姓名包含无效字符", "INVALID_NAME_CHARACTERS")
    
    return clean_name.title()  # 首字母大写


def validate_twilio_form_data(form_data: Dict[str, Any]) -> Dict[str, str]:
    """验证 Twilio webhook 表单数据
    
    Args:
        form_data: 原始表单数据
        
    Returns:
        验证后的表单数据字典
        
    Raises:
        ValidationError: 表单数据验证失败
    """
    if not form_data:
        raise ValidationError("表单数据为空", "EMPTY_FORM_DATA")
    
    # 提取并验证必要字段
    try:
        body = form_data.get("Body", "")
        from_number = form_data.get("From", "")
        to_number = form_data.get("To", "")
        message_sid = form_data.get("MessageSid", "")
        
        # 验证消息内容
        if body:
            body = validate_user_message(body)
        
        # 验证电话号码格式
        if from_number:
            from_number = _validate_phone_number(from_number)
        
        if to_number:
            to_number = _validate_phone_number(to_number)
        
        # 验证消息ID
        if message_sid and not re.match(r'^[A-Za-z0-9]+$', message_sid):
            raise ValidationError("无效的消息ID格式", "INVALID_MESSAGE_SID")
        
        return {
            "body": body,
            "from": from_number,
            "to": to_number,
            "message_sid": message_sid
        }
        
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        raise ValidationError(f"表单数据验证失败: {str(e)}", "FORM_VALIDATION_ERROR")


def _validate_phone_number(phone: str) -> str:
    """验证电话号码格式
    
    Args:
        phone: 原始电话号码
        
    Returns:
        清理后的电话号码
        
    Raises:
        ValidationError: 电话号码格式无效
    """
    if not phone:
        return ""
    
    # 移除 WhatsApp 前缀
    clean_phone = phone.replace("whatsapp:", "").strip()
    
    # 只保留数字和 + 号
    clean_phone = re.sub(r'[^\d+]', '', clean_phone)
    
    # 基本格式检查
    if clean_phone and not re.match(r'^\+?[\d]{8,15}$', clean_phone):
        raise ValidationError("电话号码格式无效", "INVALID_PHONE_FORMAT")
    
    return clean_phone


def validate_json_order(order_json: str) -> Dict[str, Any]:
    """验证订单JSON格式和内容
    
    Args:
        order_json: JSON格式的订单字符串
        
    Returns:
        验证后的订单数据
        
    Raises:
        ValidationError: 订单验证失败
    """
    import json
    
    if not order_json or not order_json.strip():
        raise ValidationError("订单JSON不能为空", "EMPTY_ORDER_JSON")
    
    try:
        order_data = json.loads(order_json)
    except json.JSONDecodeError as e:
        raise ValidationError(f"订单JSON格式无效: {str(e)}", "INVALID_JSON_FORMAT")
    
    # 验证订单结构
    if not isinstance(order_data, dict):
        raise ValidationError("订单数据必须是对象格式", "INVALID_ORDER_STRUCTURE")
    
    # 检查必需字段
    if "items" not in order_data:
        raise ValidationError("订单缺少items字段", "MISSING_ITEMS_FIELD")
    
    if "note" not in order_data:
        raise ValidationError("订单缺少note字段", "MISSING_NOTE_FIELD")
    
    # 验证items字段
    items = order_data["items"]
    if not isinstance(items, list):
        raise ValidationError("items字段必须是数组", "INVALID_ITEMS_TYPE")
    
    # 验证每个订单项目
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValidationError(f"订单项目{i}不是有效对象", "INVALID_ITEM_STRUCTURE")
        
        if "name" not in item:
            raise ValidationError(f"订单项目{i}缺少name字段", "MISSING_ITEM_NAME")
        
        if "quantity" not in item:
            raise ValidationError(f"订单项目{i}缺少quantity字段", "MISSING_ITEM_QUANTITY")
        
        # 验证商品名称
        item_name = item["name"]
        if not isinstance(item_name, str) or not item_name.strip():
            raise ValidationError(f"订单项目{i}的名称无效", "INVALID_ITEM_NAME")
        
        # 验证数量
        quantity = item["quantity"]
        if not isinstance(quantity, (int, float)) or quantity <= 0:
            raise ValidationError(f"订单项目{i}的数量必须是正数", "INVALID_ITEM_QUANTITY")
        
        if quantity > 99:  # 合理的数量上限
            raise ValidationError(f"订单项目{i}的数量过大", "QUANTITY_TOO_LARGE")
    
    # 验证note字段
    note = order_data["note"]
    if not isinstance(note, str):
        raise ValidationError("note字段必须是字符串", "INVALID_NOTE_TYPE")
    
    if len(note) > 500:  # 备注长度限制
        raise ValidationError("订单备注过长", "NOTE_TOO_LONG")
    
    return order_data


def sanitize_for_logging(text: str, max_length: int = 100) -> str:
    """为日志记录清理文本（移除敏感信息）
    
    Args:
        text: 原始文本
        max_length: 最大长度
        
    Returns:
        清理后的文本
    """
    if not text:
        return ""
    
    # 移除潜在的敏感信息模式
    sensitive_patterns = [
        r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',  # 信用卡号
        r'\b\d{3}-\d{2}-\d{4}\b',                       # SSN
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # 邮箱
    ]
    
    clean_text = text
    for pattern in sensitive_patterns:
        clean_text = re.sub(pattern, '[REDACTED]', clean_text)
    
    # 截断长度
    if len(clean_text) > max_length:
        clean_text = clean_text[:max_length] + "..."
    
    return clean_text
