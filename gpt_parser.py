"""GPT-4o 订单解析模块"""
import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletion
from utils.logger import get_logger

logger = get_logger(__name__)

load_dotenv()

openai_key = os.getenv("OPENAI_API_KEY")
if not openai_key:
    raise RuntimeError("Environment variable OPENAI_API_KEY is required but missing.")

_client = OpenAI(api_key=openai_key)

# 加载系统提示模板
prompt_path = Path("prompt_templates") / "order_prompt.txt"
if not prompt_path.exists():
    raise RuntimeError(f"系统提示模板文件不存在: {prompt_path}")

try:
    SYSTEM_PROMPT = prompt_path.read_text(encoding="utf-8").strip()
except IOError as e:
    raise RuntimeError(f"无法读取系统提示模板: {e}")

if not SYSTEM_PROMPT:
    raise RuntimeError("系统提示模板为空")


def parse_order(message: str, menu_items: List[str]) -> str:
    """使用 GPT-4o 将自然语言订单转换为 JSON 格式
    
    Args:
        message: 用户的自然语言订单消息
        menu_items: 可用的菜单项目列表
        
    Returns:
        JSON 格式的订单字符串
        
    Raises:
        ValueError: 输入参数无效
        RuntimeError: GPT API 调用失败
        json.JSONDecodeError: 返回的 JSON 格式无效
    """
    if not message or not message.strip():
        raise ValueError("订单消息不能为空")
    
    if not menu_items:
        raise ValueError("菜单项目列表不能为空")
    
    # 清理和验证菜单项目
    cleaned_menu = [item.strip() for item in menu_items if item and item.strip()]
    if not cleaned_menu:
        raise ValueError("菜单项目列表中没有有效项目")
    
    user_content = f"客户内容: {message.strip()}\n菜单列表: {json.dumps(cleaned_menu, ensure_ascii=False)}"
    
    try:
        logger.debug("发送订单解析请求到 OpenAI")
        response: ChatCompletion = _client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,  # 降低随机性，提高一致性
            max_tokens=1000,  # 限制响应长度
            timeout=30.0,  # 设置超时
        )
        
        if not response.choices:
            raise RuntimeError("GPT API 返回空响应")
        
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("GPT API 返回空内容")
        
        content = content.strip()
        logger.debug("GPT 原始输出: %s", content)
        
        # 验证返回的 JSON 格式
        try:
            parsed_json = json.loads(content)
            
            # 基本结构验证
            if not isinstance(parsed_json, dict):
                raise ValueError("返回的数据不是有效的 JSON 对象")
            
            if "items" not in parsed_json:
                raise ValueError("返回的 JSON 缺少 'items' 字段")
            
            if not isinstance(parsed_json["items"], list):
                raise ValueError("'items' 字段必须是数组")
            
            # 验证每个订单项目
            for i, item in enumerate(parsed_json["items"]):
                if not isinstance(item, dict):
                    raise ValueError(f"订单项目 {i} 不是有效的对象")
                
                if "name" not in item:
                    raise ValueError(f"订单项目 {i} 缺少 'name' 字段")
                
                if "quantity" not in item:
                    raise ValueError(f"订单项目 {i} 缺少 'quantity' 字段")
                
                if not isinstance(item["quantity"], (int, float)) or item["quantity"] <= 0:
                    raise ValueError(f"订单项目 {i} 的数量必须是正数")
            
            logger.info("成功解析订单，包含 %d 个项目", len(parsed_json["items"]))
            return content
            
        except json.JSONDecodeError as e:
            logger.error("GPT 返回的内容不是有效 JSON: %s", content)
            raise json.JSONDecodeError(f"GPT 返回无效 JSON: {e}", content, 0)
        
    except Exception as e:
        if isinstance(e, (ValueError, json.JSONDecodeError)):
            raise
        logger.exception("GPT 订单解析失败")
        raise RuntimeError(f"GPT API 调用失败: {e}")


def validate_order_json(order_json: str) -> Dict[str, Any]:
    """验证并解析订单 JSON
    
    Args:
        order_json: JSON 格式的订单字符串
        
    Returns:
        解析后的订单字典
        
    Raises:
        json.JSONDecodeError: JSON 格式无效
        ValueError: 订单数据结构无效
    """
    try:
        order_data = json.loads(order_json)
    except json.JSONDecodeError as e:
        logger.error("订单 JSON 解析失败: %s", order_json)
        raise
    
    if not isinstance(order_data, dict):
        raise ValueError("订单数据必须是对象")
    
    if "items" not in order_data or not isinstance(order_data["items"], list):
        raise ValueError("订单必须包含 'items' 数组")
    
    if not order_data["items"]:
        raise ValueError("订单至少需要包含一个商品")
    
    return order_data


def get_menu_item_names(menu_data: Dict[str, Any]) -> List[str]:
    """从菜单数据中提取商品名称列表
    
    Args:
        menu_data: 菜单数据字典
        
    Returns:
        商品名称列表
    """
    if not isinstance(menu_data, dict) or "items" not in menu_data:
        logger.warning("菜单数据格式无效")
        return []
    
    items = menu_data.get("items", [])
    if not isinstance(items, list):
        logger.warning("菜单项目不是数组格式")
        return []
    
    names = []
    for item in items:
        if isinstance(item, dict) and "name" in item:
            name = item["name"]
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    
    logger.debug("提取到 %d 个菜单项目名称", len(names))
    return names
