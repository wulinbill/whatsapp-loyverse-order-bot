"""GPT-4o 订单解析模块 - 根据新prompt优化版本"""
import os
import json
import re
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


def _clean_gpt_response(content: str) -> str:
    """清理 GPT 响应，移除 markdown 代码块标记和多余内容
    
    Args:
        content: GPT 的原始响应内容
        
    Returns:
        清理后的 JSON 字符串
    """
    content = content.strip()
    
    # 移除可能的说明文字和markdown标记
    lines = content.split('\n')
    json_lines = []
    in_json = False
    
    for line in lines:
        line = line.strip()
        
        # 跳过空行
        if not line:
            continue
            
        # 检测JSON开始
        if line.startswith('{'):
            in_json = True
            json_lines.append(line)
        elif in_json:
            json_lines.append(line)
            # 检测JSON结束
            if line.endswith('}') and line.count('}') >= line.count('{'):
                break
    
    if json_lines:
        content = '\n'.join(json_lines)
    
    # 移除 markdown 代码块标记
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    
    if content.endswith("```"):
        content = content[:-3]
    
    # 移除多余的空白字符
    content = content.strip()
    
    # 尝试提取JSON对象
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        content = json_match.group(0)
    
    return content


def _validate_order_structure(order_data: Dict[str, Any]) -> None:
    """验证订单数据结构符合新prompt要求
    
    Args:
        order_data: 订单数据字典
        
    Raises:
        ValueError: 订单结构不符合要求
    """
    # 检查必需字段
    required_fields = ["items", "note"]
    for field in required_fields:
        if field not in order_data:
            raise ValueError(f"订单缺少必需字段: {field}")
    
    # 验证items字段
    items = order_data["items"]
    if not isinstance(items, list):
        raise ValueError("'items' 字段必须是数组")
    
    # 验证每个订单项目
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"订单项目 {i} 不是有效的对象")
        
        if "name" not in item:
            raise ValueError(f"订单项目 {i} 缺少 'name' 字段")
        
        if "quantity" not in item:
            raise ValueError(f"订单项目 {i} 缺少 'quantity' 字段")
        
        if not isinstance(item["quantity"], (int, float)) or item["quantity"] <= 0:
            raise ValueError(f"订单项目 {i} 的数量必须是正数")
        
        # 验证名称不为空
        if not isinstance(item["name"], str) or not item["name"].strip():
            raise ValueError(f"订单项目 {i} 的名称不能为空")
    
    # 验证note字段
    if not isinstance(order_data["note"], str):
        raise ValueError("'note' 字段必须是字符串")


def parse_order(message: str, menu_items: List[str]) -> str:
    """使用 GPT-4o 将自然语言订单转换为 JSON 格式
    
    根据新的prompt模板，支持多语言(es/en/zh)订单解析，
    自动处理Combinaciones配菜、Adicionales等复杂逻辑。
    
    Args:
        message: 用户的自然语言订单消息
        menu_items: 可用的菜单项目列表
        
    Returns:
        JSON 格式的订单字符串，结构为:
        {"items": [{"name": "...", "quantity": ...}], "note": "..."}
        
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
    
    # 构建用户内容，包含菜单信息
    user_content = f"客户内容: {message.strip()}\n菜单列表: {json.dumps(cleaned_menu, ensure_ascii=False)}"
    
    try:
        logger.debug("发送订单解析请求到 OpenAI")
        logger.debug("用户消息: %s", message.strip())
        logger.debug("菜单项目数量: %d", len(cleaned_menu))
        
        response: ChatCompletion = _client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,  # 降低随机性，提高一致性
            max_tokens=1500,  # 增加token限制以处理复杂订单
            timeout=30.0,  # 设置超时
        )
        
        if not response.choices:
            raise RuntimeError("GPT API 返回空响应")
        
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("GPT API 返回空内容")
        
        logger.debug("GPT 原始输出: %s", content)
        
        # 清理响应内容
        cleaned_content = _clean_gpt_response(content)
        logger.debug("清理后的内容: %s", cleaned_content)
        
        # 验证返回的 JSON 格式
        try:
            parsed_json = json.loads(cleaned_content)
            
            # 验证订单结构
            _validate_order_structure(parsed_json)
            
            logger.info("成功解析订单，包含 %d 个项目", len(parsed_json["items"]))
            
            # 记录解析结果详情
            if parsed_json["items"]:
                for i, item in enumerate(parsed_json["items"]):
                    logger.debug("项目 %d: %s x%s", i+1, item["name"], item["quantity"])
            
            if parsed_json["note"]:
                logger.debug("订单备注: %s", parsed_json["note"])
            
            return cleaned_content
            
        except json.JSONDecodeError as e:
            logger.error("清理后的内容仍不是有效 JSON: %s", cleaned_content)
            
            # 尝试更积极的JSON提取
            try:
                # 查找所有可能的JSON对象
                json_patterns = [
                    r'\{[^{}]*"items"[^{}]*\[[^\]]*\][^{}]*\}',  # 简单JSON
                    r'\{.*?"items".*?\[.*?\].*?\}',              # 更复杂的JSON
                ]
                
                for pattern in json_patterns:
                    matches = re.findall(pattern, cleaned_content, re.DOTALL)
                    for match in matches:
                        try:
                            potential_json = json.loads(match)
                            _validate_order_structure(potential_json)
                            logger.info("成功提取并验证 JSON")
                            return match
                        except (json.JSONDecodeError, ValueError):
                            continue
                
                # 如果所有方法都失败，返回错误格式
                error_response = {
                    "items": [],
                    "note": "解析失败，请重新下单 / Parse failed, please reorder / Análisis falló, vuelva a ordenar"
                }
                logger.warning("所有JSON提取方法失败，返回错误响应")
                return json.dumps(error_response, ensure_ascii=False)
                
            except Exception as extract_error:
                logger.error("JSON提取过程出错: %s", extract_error)
                raise json.JSONDecodeError(f"GPT 返回无效 JSON: {e}", cleaned_content, 0)
        
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
    
    # 使用统一的结构验证
    _validate_order_structure(order_data)
    
    return order_data


def get_menu_item_names(menu_data: Dict[str, Any]) -> List[str]:
    """从菜单数据中提取商品名称列表 - 优化版本
    
    根据新prompt的要求，需要支持按category分类的菜单结构，
    包括Combinaciones、MINI Combinaciones、Acompañantes、Adicionales等。
    
    Args:
        menu_data: 菜单数据字典
        
    Returns:
        商品名称列表，包含所有可用的菜单项目
    """
    logger.debug("开始解析菜单数据，数据类型: %s", type(menu_data))
    
    if not isinstance(menu_data, dict):
        logger.warning("菜单数据不是字典格式: %s", type(menu_data))
        return []
    
    logger.debug("菜单数据包含的键: %s", list(menu_data.keys()))
    
    names = []
    
    # 检查不同可能的结构
    items_sources = []
    
    # 标准结构：{"items": [...]}
    if "items" in menu_data and isinstance(menu_data["items"], list):
        items_sources.append(("items", menu_data["items"]))
    
    # 按类别分组的结构：{"categories": [...]} 或直接的类别键
    category_keys = ["categories", "menu_items", "products"]
    for key in category_keys:
        if key in menu_data and isinstance(menu_data[key], list):
            items_sources.append((key, menu_data[key]))
    
    # 如果菜单数据本身就是列表
    if isinstance(menu_data, list):
        items_sources.append(("root", menu_data))
    
    # 处理所有找到的项目源
    for source_name, items in items_sources:
        logger.debug("处理来源 '%s'，项目数量: %d", source_name, len(items))
        
        for i, item in enumerate(items):
            try:
                extracted_names = _extract_names_from_item(item, i, source_name)
                names.extend(extracted_names)
                        
            except Exception as e:
                logger.warning("处理菜单项目 %d (来源: %s) 时出错: %s", i, source_name, e)
                continue
    
    # 去重并保持顺序
    unique_names = []
    seen = set()
    for name in names:
        if name not in seen:
            unique_names.append(name)
            seen.add(name)
    
    logger.info("成功提取到 %d 个唯一菜单项目名称", len(unique_names))
    
    if not unique_names:
        logger.error("未能从菜单数据中提取任何名称！")
        _debug_menu_structure_summary(menu_data)
    
    return unique_names


def _extract_names_from_item(item: Any, index: int, source: str) -> List[str]:
    """从单个菜单项目中提取名称
    
    Args:
        item: 菜单项目数据
        index: 项目索引
        source: 数据源名称
        
    Returns:
        提取到的名称列表
    """
    names = []
    
    if isinstance(item, dict):
        # 处理带类别的结构
        if "category" in item and "items" in item:
            category = item["category"]
            category_items = item["items"]
            if isinstance(category_items, list):
                logger.debug("处理类别 '%s'，包含 %d 个项目", category, len(category_items))
                for sub_item in category_items:
                    sub_names = _extract_name_from_dict(sub_item)
                    names.extend(sub_names)
        else:
            # 直接处理项目字典
            item_names = _extract_name_from_dict(item)
            names.extend(item_names)
            
    elif isinstance(item, str) and item.strip():
        # 直接的字符串名称
        names.append(item.strip())
        logger.debug("项目 %d (来源: %s): 字符串名称 '%s'", index, source, item.strip())
    else:
        logger.debug("项目 %d (来源: %s): 未识别类型 %s", index, source, type(item))
    
    return names


def _extract_name_from_dict(item_dict: Dict[str, Any]) -> List[str]:
    """从字典中提取名称字段
    
    Args:
        item_dict: 项目字典
        
    Returns:
        提取到的名称列表
    """
    names = []
    
    # 常见的名称字段，按优先级排序
    name_fields = [
        "name", "item_name", "product_name", "title", 
        "display_name", "menu_name", "dish_name"
    ]
    
    for name_field in name_fields:
        if name_field in item_dict:
            name_value = item_dict[name_field]
            if isinstance(name_value, str) and name_value.strip():
                names.append(name_value.strip())
                break
    
    # 如果还是没找到名称，尝试其他可能的字段
    if not names:
        for key, value in item_dict.items():
            if isinstance(value, str) and value.strip() and len(value) < 100:
                # 简单启发式：字符串长度合理且不是明显的非名称字段
                non_name_keys = {"id", "price", "description", "category", "type", "url", "image"}
                if key.lower() not in non_name_keys:
                    names.append(value.strip())
                    logger.debug("使用启发式提取名称字段 '%s': '%s'", key, value.strip())
                    break
    
    return names


def _debug_menu_structure_summary(menu_data: Dict[str, Any]) -> None:
    """记录菜单结构摘要用于调试"""
    logger.error("菜单数据结构摘要:")
    logger.error("  - 数据类型: %s", type(menu_data))
    
    if isinstance(menu_data, dict):
        logger.error("  - 主要键: %s", list(menu_data.keys()))
        
        # 检查常见的数据结构
        for key in ["items", "categories", "menu_items", "products"]:
            if key in menu_data:
                value = menu_data[key]
                logger.error("  - 键 '%s': 类型=%s", key, type(value))
                if isinstance(value, list) and value:
                    logger.error("    - 长度: %d", len(value))
                    logger.error("    - 第一个元素类型: %s", type(value[0]))
                    if isinstance(value[0], dict):
                        logger.error("    - 第一个元素键: %s", list(value[0].keys()))
                        sample = json.dumps(value[0], ensure_ascii=False, indent=4)
                        logger.error("    - 第一个元素样本: %s", sample[:300] + "..." if len(sample) > 300 else sample)


def debug_menu_structure(menu_data: Dict[str, Any]) -> None:
    """调试菜单数据结构 - 详细版本"""
    print("=== 菜单数据结构调试 (详细版) ===")
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
                        
                        # 显示前2个元素的完整结构
                        for i, item in enumerate(value[:2]):
                            print(f"  元素 {i}: {json.dumps(item, ensure_ascii=False, indent=6)}")
                            
                    elif isinstance(value[0], str):
                        print(f"  前5个字符串元素: {value[:5]}")
                        
            elif isinstance(value, dict):
                print(f"  子键: {list(value.keys())}")
                print(f"  内容摘要: {json.dumps(value, ensure_ascii=False, indent=4)[:200]}...")
            else:
                print(f"  值: {str(value)[:100]}")
    
    print("=" * 50)