"""优化后的 GPT-4o 订单解析模块"""
import os
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletion

from config import settings
from utils.logger import get_logger
from utils.validators import validate_json_order, ValidationError

logger = get_logger(__name__)

load_dotenv()

# 使用配置管理的设置
openai_key = settings.openai_api_key
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


class OrderParsingError(Exception):
    """订单解析专用异常"""
    def __init__(self, message: str, error_code: str = None, original_error: Exception = None):
        self.message = message
        self.error_code = error_code
        self.original_error = original_error
        super().__init__(self.message)


def _clean_gpt_response(content: str) -> str:
    """清理 GPT 响应，移除 markdown 代码块标记和多余内容
    
    使用更高效的正则表达式处理。
    
    Args:
        content: GPT 的原始响应内容
        
    Returns:
        清理后的 JSON 字符串
    """
    if not content:
        return ""
    
    content = content.strip()
    
    # 使用正则表达式一次性移除 markdown 标记
    content = re.sub(r'^```(?:json)?\n?', '', content, flags=re.MULTILINE)
    content = re.sub(r'\n?```$', '', content, flags=re.MULTILINE)
    
    # 尝试提取JSON对象（贪婪匹配）
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        content = json_match.group(0)
    
    return content.strip()


def _validate_order_structure(order_data: Dict[str, Any]) -> None:
    """验证订单数据结构符合新prompt要求
    
    Args:
        order_data: 订单数据字典
        
    Raises:
        ValidationError: 订单结构不符合要求
    """
    # 使用统一的验证器
    try:
        # 先转换为JSON字符串再验证，确保使用统一的验证逻辑
        json_str = json.dumps(order_data, ensure_ascii=False)
        validate_json_order(json_str)
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(f"订单结构验证失败: {str(e)}", "STRUCTURE_VALIDATION_ERROR")


def _auto_fix_json(content: str) -> Optional[str]:
    """尝试自动修复常见的JSON格式问题
    
    Args:
        content: 可能有问题的JSON字符串
        
    Returns:
        修复后的JSON字符串，如果无法修复则返回None
    """
    if not content or not content.strip():
        return None
    
    content = content.strip()
    
    # 修复1: 确保以 { 开始，以 } 结束
    if content.startswith("{") and not content.endswith("}"):
        content = content + "}"
    
    # 修复2: 添加缺失的 note 字段
    if '"items"' in content and '"note"' not in content:
        # 移除尾部的 }
        if content.endswith('}'):
            content = content[:-1]
        
        # 移除尾部的逗号（如果有）
        content = content.rstrip().rstrip(',')
        
        # 添加 note 字段
        content += ', "note": ""}'
    
    # 修复3: 处理多余的逗号
    content = re.sub(r',\s*}', '}', content)
    content = re.sub(r',\s*]', ']', content)
    
    # 修复4: 确保字符串正确引用
    # 这是一个简单的修复，复杂情况可能需要更高级的解析
    content = re.sub(r'(\w+):', r'"\1":', content)  # 为未引用的键添加引号
    
    try:
        # 验证修复后的JSON
        parsed = json.loads(content)
        _validate_order_structure(parsed)
        return content
    except Exception:
        return None


def parse_order(message: str, menu_items: List[str]) -> str:
    """使用 GPT-4o 将自然语言订单转换为 JSON 格式
    
    优化版本：
    - 使用配置管理的参数
    - 更好的错误处理
    - 自动修复常见JSON问题
    - 更详细的日志记录
    
    Args:
        message: 用户的自然语言订单消息
        menu_items: 可用的菜单项目列表
        
    Returns:
        JSON 格式的订单字符串
        
    Raises:
        OrderParsingError: 订单解析失败
    """
    if not message or not message.strip():
        raise OrderParsingError("订单消息不能为空", "EMPTY_MESSAGE")
    
    if not menu_items:
        raise OrderParsingError("菜单项目列表不能为空", "EMPTY_MENU")
    
    # 清理和验证菜单项目
    cleaned_menu = [item.strip() for item in menu_items if item and item.strip()]
    if not cleaned_menu:
        raise OrderParsingError("菜单项目列表中没有有效项目", "NO_VALID_MENU_ITEMS")
    
    # 构建用户内容
    user_content = f"客户内容: {message.strip()}\n菜单列表: {json.dumps(cleaned_menu, ensure_ascii=False)}"
    
    # 记录请求信息
    logger.debug("发送订单解析请求到 OpenAI")
    logger.debug("用户消息: %s", message.strip()[:200])  # 限制日志长度
    logger.debug("菜单项目数量: %d", len(cleaned_menu))
    
    try:
        # 调用 OpenAI API
        response: ChatCompletion = _client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=settings.openai_temperature,
            max_tokens=settings.openai_max_tokens,
            timeout=settings.openai_timeout,
        )
        
        if not response.choices:
            raise OrderParsingError("GPT API 返回空响应", "EMPTY_API_RESPONSE")
        
        content = response.choices[0].message.content
        if not content:
            raise OrderParsingError("GPT API 返回空内容", "EMPTY_API_CONTENT")
        
        logger.debug("GPT 原始输出长度: %d 字符", len(content))
        
        # 清理响应内容
        cleaned_content = _clean_gpt_response(content)
        logger.debug("清理后内容长度: %d 字符", len(cleaned_content))
        
        # 验证 JSON 格式
        try:
            parsed_json = json.loads(cleaned_content)
            _validate_order_structure(parsed_json)
            
            # 记录成功解析的详情
            items_count = len(parsed_json.get("items", []))
            logger.info("成功解析订单，包含 %d 个项目", items_count)
            
            if settings.debug_mode:
                for i, item in enumerate(parsed_json.get("items", [])):
                    logger.debug("项目 %d: %s x%s", i+1, 
                               item.get("name", ""), item.get("quantity", ""))
                
                note = parsed_json.get("note", "")
                if note:
                    logger.debug("订单备注: %s", note[:100])
            
            return cleaned_content
            
        except json.JSONDecodeError as json_error:
            logger.warning("JSON 解析失败，尝试自动修复")
            
            # 尝试自动修复
            fixed_content = _auto_fix_json(cleaned_content)
            if fixed_content:
                try:
                    parsed_json = json.loads(fixed_content)
                    _validate_order_structure(parsed_json)
                    logger.info("自动修复 JSON 成功")
                    return fixed_content
                except Exception as fix_error:
                    logger.warning("自动修复后仍然无效: %s", str(fix_error))
            
            # 修复失败，抛出详细错误
            logger.error("JSON 解析失败，原始内容: %s", cleaned_content[:500])
            raise OrderParsingError(
                f"GPT 返回的内容不是有效的 JSON 格式: {str(json_error)}",
                "INVALID_JSON_FORMAT",
                json_error
            )
            
        except ValidationError as validation_error:
            logger.error("订单结构验证失败: %s", validation_error.message)
            raise OrderParsingError(
                f"订单数据结构无效: {validation_error.message}",
                "INVALID_ORDER_STRUCTURE",
                validation_error
            )
        
    except OrderParsingError:
        # 重新抛出我们自己的异常
        raise
    except Exception as e:
        logger.exception("GPT 订单解析过程中出现意外错误")
        raise OrderParsingError(
            f"订单解析失败: {str(e)}",
            "UNEXPECTED_ERROR",
            e
        )


def validate_order_json(order_json: str) -> Dict[str, Any]:
    """验证并解析订单 JSON
    
    这个函数现在是 utils.validators.validate_json_order 的包装器，
    保持向后兼容性。
    
    Args:
        order_json: JSON 格式的订单字符串
        
    Returns:
        解析后的订单字典
        
    Raises:
        json.JSONDecodeError: JSON 格式无效
        ValidationError: 订单数据结构无效
    """
    try:
        return validate_json_order(order_json)
    except Exception as e:
        logger.error("订单 JSON 验证失败: %s", str(e))
        raise


def get_menu_item_names(menu_data: Dict[str, Any]) -> List[str]:
    """从菜单数据中提取商品名称列表 - 优化版本
    
    使用缓存和更高效的数据处理。
    
    Args:
        menu_data: 菜单数据字典
        
    Returns:
        商品名称列表，包含所有可用的菜单项目
    """
    if not isinstance(menu_data, dict):
        logger.warning("菜单数据不是字典格式: %s", type(menu_data))
        return []
    
    logger.debug("开始解析菜单数据，包含键: %s", list(menu_data.keys()))
    
    names = []
    
    # 处理不同的菜单结构
    items_sources = []
    
    # 标准结构：{"items": [...]}
    if "items" in menu_data and isinstance(menu_data["items"], list):
        items_sources.append(("items", menu_data["items"]))
    
    # 按类别分组的结构
    for key in ["categories", "menu_items", "products"]:
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
                logger.warning("处理菜单项目 %d (来源: %s) 时出错: %s", i, source_name, str(e))
                continue
    
    # 去重并保持顺序
    unique_names = list(dict.fromkeys(names))  # 保持顺序的去重方法
    
    logger.info("成功提取到 %d 个唯一菜单项目名称", len(unique_names))
    
    if not unique_names:
        logger.error("未能从菜单数据中提取任何名称！")
        if settings.debug_mode:
            _debug_menu_structure_summary(menu_data)
    
    return unique_names


def _extract_names_from_item(item: Any, index: int, source: str) -> List[str]:
    """从单个菜单项目中提取名称
    
    优化版本，使用更有效的字符串处理。
    
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
            category_items = item["items"]
            if isinstance(category_items, list):
                logger.debug("处理类别 '%s'，包含 %d 个项目", 
                           item["category"], len(category_items))
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
    
    优化版本，使用更高效的字段查找。
    
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
    
    # 优先查找标准名称字段
    for name_field in name_fields:
        name_value = item_dict.get(name_field)
        if isinstance(name_value, str) and name_value.strip():
            names.append(name_value.strip())
            return names  # 找到就返回，不继续查找
    
    # 启发式查找：寻找可能的名称字段
    non_name_keys = {
        "id", "price", "description", "category", "type", "url", "image",
        "cost", "amount", "quantity", "variants", "options", "created_at",
        "updated_at", "deleted", "active", "available"
    }
    
    for key, value in item_dict.items():
        if (isinstance(value, str) and 
            value.strip() and 
            len(value) < 100 and  # 合理的名称长度
            key.lower() not in non_name_keys):
            
            names.append(value.strip())
            logger.debug("使用启发式提取名称字段 '%s': '%s'", key, value.strip())
            break  # 只取第一个符合条件的
    
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
                        # 只显示前200字符避免日志过长
                        sample = json.dumps(value[0], ensure_ascii=False, indent=4)
                        if len(sample) > 200:
                            sample = sample[:200] + "..."
                        logger.error("    - 第一个元素样本: %s", sample)


def debug_menu_structure(menu_data: Dict[str, Any]) -> None:
    """调试菜单数据结构 - 详细版本（仅在调试模式下使用）"""
    if not settings.debug_mode:
        return
        
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
                content_preview = json.dumps(value, ensure_ascii=False, indent=4)[:200]
                print(f"  内容摘要: {content_preview}...")
            else:
                print(f"  值: {str(value)[:100]}")
    
    print("=" * 50)


# 性能优化：缓存常用的菜单名称提取结果
_menu_names_cache = {}
_cache_max_size = 10

def get_cached_menu_names(menu_data: Dict[str, Any]) -> List[str]:
    """获取缓存的菜单名称，提高重复调用的性能"""
    global _menu_names_cache
    
    # 生成缓存键（基于菜单数据的哈希）
    try:
        menu_str = json.dumps(menu_data, sort_keys=True, ensure_ascii=False)
        cache_key = hash(menu_str)
    except (TypeError, ValueError):
        # 如果无法序列化，直接调用原函数
        return get_menu_item_names(menu_data)
    
    # 检查缓存
    if cache_key in _menu_names_cache:
        logger.debug("使用缓存的菜单名称")
        return _menu_names_cache[cache_key]
    
    # 计算新结果
    result = get_menu_item_names(menu_data)
    
    # 添加到缓存（限制缓存大小）
    if len(_menu_names_cache) >= _cache_max_size:
        # 移除最旧的条目
        oldest_key = next(iter(_menu_names_cache))
        del _menu_names_cache[oldest_key]
    
    _menu_names_cache[cache_key] = result
    logger.debug("菜单名称已添加到缓存")
    
    return result


def clear_menu_cache():
    """清除菜单名称缓存"""
    global _menu_names_cache
    _menu_names_cache.clear()
    logger.debug("菜单名称缓存已清除")


# 统计和监控功能
class OrderParsingStats:
    """订单解析统计"""
    
    def __init__(self):
        self.total_requests = 0
        self.successful_parses = 0
        self.failed_parses = 0
        self.auto_fixes = 0
        self.cache_hits = 0
    
    def record_request(self):
        self.total_requests += 1
    
    def record_success(self):
        self.successful_parses += 1
    
    def record_failure(self):
        self.failed_parses += 1
    
    def record_auto_fix(self):
        self.auto_fixes += 1
    
    def record_cache_hit(self):
        self.cache_hits += 1
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_parses": self.successful_parses,
            "failed_parses": self.failed_parses,
            "auto_fixes": self.auto_fixes,
            "cache_hits": self.cache_hits,
            "success_rate": (
                self.successful_parses / max(self.total_requests, 1) * 100
            ),
            "auto_fix_rate": (
                self.auto_fixes / max(self.failed_parses, 1) * 100
            )
        }
    
    def reset(self):
        self.__init__()


# 全局统计实例
parsing_stats = OrderParsingStats()


def get_parsing_stats() -> Dict[str, Any]:
    """获取解析统计信息"""
    return parsing_stats.get_stats()


def reset_parsing_stats():
    """重置解析统计"""
    parsing_stats.reset()
    logger.info("订单解析统计已重置")
