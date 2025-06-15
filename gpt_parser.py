"""GPT-4o 订单解析模块 - 改进版本"""
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
    """从菜单数据中提取商品名称列表 - 改进版本
    
    Args:
        menu_data: 菜单数据字典
        
    Returns:
        商品名称列表
    """
    logger.debug("开始解析菜单数据，数据类型: %s", type(menu_data))
    
    if not isinstance(menu_data, dict):
        logger.warning("菜单数据不是字典格式: %s", type(menu_data))
        return []
    
    logger.debug("菜单数据包含的键: %s", list(menu_data.keys()))
    
    # 检查不同可能的结构
    items = None
    
    # 标准结构：{"items": [...]}
    if "items" in menu_data:
        items = menu_data["items"]
        logger.debug("找到 'items' 键，类型: %s", type(items))
    
    # 备选结构：{"data": [...]} 或直接是数组
    elif "data" in menu_data:
        items = menu_data["data"]
        logger.debug("找到 'data' 键，类型: %s", type(items))
    
    # 如果菜单数据本身就是列表
    elif isinstance(menu_data, list):
        items = menu_data
        logger.debug("菜单数据本身是列表")
    
    if not isinstance(items, list):
        logger.warning("菜单项目不是数组格式，实际类型: %s", type(items))
        if items is not None:
            logger.debug("菜单项目内容前100字符: %s", str(items)[:100])
        return []
    
    logger.debug("菜单项目数量: %d", len(items))
    
    names = []
    for i, item in enumerate(items):
        try:
            if isinstance(item, dict):
                # 寻找名称字段的不同可能性
                name = None
                
                # 常见的名称字段
                for name_key in ["name", "item_name", "product_name", "title", "display_name"]:
                    if name_key in item:
                        name = item[name_key]
                        break
                
                if name and isinstance(name, str) and name.strip():
                    names.append(name.strip())
                    logger.debug("项目 %d: 提取名称 '%s'", i, name.strip())
                else:
                    logger.debug("项目 %d: 未找到有效名称，键: %s", i, list(item.keys()) if isinstance(item, dict) else "非字典")
                    
                    # 如果没有找到名称字段，记录项目结构用于调试
                    if i < 3:  # 只记录前3个项目避免日志过多
                        logger.debug("项目 %d 结构: %s", i, json.dumps(item, ensure_ascii=False, indent=2)[:200])
            else:
                logger.debug("项目 %d 不是字典格式: %s", i, type(item))
                
        except Exception as e:
            logger.warning("处理菜单项目 %d 时出错: %s", i, e)
            continue
    
    logger.info("成功提取到 %d 个菜单项目名称", len(names))
    
    if not names:
        logger.error("未能从菜单数据中提取任何名称！")
        logger.error("菜单数据结构摘要:")
        logger.error("  - 数据类型: %s", type(menu_data))
        logger.error("  - 主要键: %s", list(menu_data.keys()) if isinstance(menu_data, dict) else "不适用")
        if isinstance(menu_data, dict) and "items" in menu_data:
            items_sample = menu_data["items"][:2] if isinstance(menu_data["items"], list) else menu_data["items"]
            logger.error("  - 前2个项目样本: %s", json.dumps(items_sample, ensure_ascii=False, indent=2)[:500])
    
    return names


def debug_menu_structure(menu_data: Dict[str, Any]) -> None:
    """调试菜单数据结构 - 辅助函数"""
    print("=== 菜单数据结构调试 ===")
    print(f"数据类型: {type(menu_data)}")
    
    if isinstance(menu_data, dict):
        print(f"顶级键: {list(menu_data.keys())}")
        
        for key, value in menu_data.items():
            print(f"\n键 '{key}':")
            print(f"  类型: {type(value)}")
            if isinstance(value, list):
                print(f"  长度: {len(value)}")
                if value:
                    print(f"  第一个元素类型: {type(value[0])}")
                    if isinstance(value[0], dict):
                        print(f"  第一个元素键: {list(value[0].keys())}")
                        print(f"  第一个元素: {json.dumps(value[0], ensure_ascii=False, indent=4)[:300]}")
            elif isinstance(value, dict):
                print(f"  子键: {list(value.keys())}")
            else:
                print(f"  值: {str(value)[:100]}")
    
    print("=" * 30)