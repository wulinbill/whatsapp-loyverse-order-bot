"""Loyverse POS API 封装模块 - 修复版"""
import os
import httpx
import json
from pathlib import Path
from typing import Dict, Any, Optional
from loyverse_auth import get_access_token
from utils.logger import get_logger
from unicodedata import normalize
from difflib import get_close_matches
import time

logger = get_logger(__name__)

LOYVERSE_API_URL = "https://api.loyverse.com/v1.0"
STORE_ID = os.getenv("LOYVERSE_STORE_ID")

if not STORE_ID:
    raise RuntimeError("Environment variable LOYVERSE_STORE_ID is required but missing.")


# ---------------------------------------------------------------------------
# In-memory menu cache & name→id index
# ---------------------------------------------------------------------------

_MENU_CACHE: Optional[Dict[str, Any]] = None  # raw menu json
_NAME2ID: Dict[str, str] = {}
_CACHE_TS: float = 0.0
# 默认 10 分钟，可通过环境变量覆盖
CACHE_TTL = int(os.getenv("LOYVERSE_MENU_CACHE_TTL", "600"))

# 对外暴露只读视图，供其他模块快速查表

def get_name_to_id_mapping() -> Dict[str, str]:
    """Return current item-name → id index (already normalized)."""
    return _NAME2ID

# Backward-compat alias (external modules may do `from loyverse_api import name2id`)
name2id = _NAME2ID

async def _get_headers() -> Dict[str, str]:
    """获取 API 请求头
    
    Returns:
        包含授权信息的请求头字典
        
    Raises:
        RuntimeError: 无法获取访问令牌
    """
    token = await get_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


async def get_menu_items(cache_path: str = "menu_data.json", force_refresh: bool = False) -> Dict[str, Any]:
    """获取菜单项目（带本地缓存）
    
    Args:
        cache_path: 缓存文件路径
        force_refresh: True 时忽略 TTL 强制刷新
        
    Returns:
        包含菜单项目的字典
        
    Raises:
        httpx.HTTPError: API 请求失败
        json.JSONDecodeError: JSON 解析失败
    """
    global _MENU_CACHE, _NAME2ID, _CACHE_TS

    # 内存缓存 + TTL
    if _MENU_CACHE and not force_refresh and (time.time() - _CACHE_TS < CACHE_TTL):
        logger.debug("使用内存缓存的菜单 (age %.1fs)", time.time() - _CACHE_TS)
        return _MENU_CACHE

    cache_file = Path(cache_path)
    # 尝试磁盘缓存（仅在内存不存在时）
    if not force_refresh and cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                _MENU_CACHE = json.load(f)
            _CACHE_TS = time.time()
            logger.debug("从磁盘缓存加载菜单 - %d 个项目", len(_MENU_CACHE.get("items", [])))
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("缓存文件读取失败: %s，将从 API 重新获取", e)
            _MENU_CACHE = None

    if _MENU_CACHE and not force_refresh:
        # 仍需要确保 _NAME2ID 已构建
        if not _NAME2ID:
            _build_name_index(_MENU_CACHE)
        return _MENU_CACHE

    # 从 API 获取菜单
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{LOYVERSE_API_URL}/items",
                headers=await _get_headers(),
                params={"limit": 250, "deleted": False},
                timeout=15.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("获取菜单失败，HTTP状态码: %d, 响应: %s", 
                        e.response.status_code, e.response.text)
            raise
        except httpx.TimeoutException as e:
            logger.error("获取菜单超时")
            raise
        
        data = response.json()
        
        # 验证响应数据
        if not isinstance(data, dict) or "items" not in data:
            raise ValueError("API 返回的菜单数据格式无效")
        
        # 更新内存缓存 & TS
        _MENU_CACHE = data
        _CACHE_TS = time.time()

        # 建立 name → id 索引
        _build_name_index(data)

        # 写入磁盘缓存（忽略写入失败）
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("菜单已缓存到磁盘 - %d 个项目", len(data.get("items", [])))
        except IOError as e:
            logger.warning("无法保存菜单缓存: %s", e)
        
        return data


def _build_name_index(menu_data: Dict[str, Any]) -> None:
    """(Re)build the global `_NAME2ID` index from fresh menu json."""
    _NAME2ID.clear()
    for itm in menu_data.get("items", []):
        base_key = _normalize_name(itm.get("name", ""))
        variants = itm.get("variants", []) or []

        # 确定变体 ID 字段名（API 里常用 id 或 variant_id）
        def _extract_var_id(obj: Dict[str, Any]):
            return obj.get("id") or obj.get("variant_id")

        # 如果有 variants，优先把主名映射到第一变体 ID；否则回退到 item.id
        if base_key:
            if variants:
                _NAME2ID[base_key] = _extract_var_id(variants[0])
            else:
                _NAME2ID[base_key] = itm.get("id")

        # 把每个变体的组合名称加入索引
        for var in variants:
            var_name_raw = var.get("name") or var.get("variant_name") or ""
            if not var_name_raw:
                continue
            var_key = _normalize_name(f"{itm.get('name', '')} {var_name_raw}")
            var_id = _extract_var_id(var)
            if var_key and var_id:
                _NAME2ID[var_key] = var_id

    logger.debug("已建立 name→id 索引，共 %d 项", len(_NAME2ID))


def _transform_order_to_receipt(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """将订单数据转换为 Loyverse 收据格式
    
    Args:
        order_data: 原始订单数据
        
    Returns:
        符合 Loyverse API 格式的收据数据
    """
    receipt_data = {
        "store_id": STORE_ID,
        "line_items": [],
        "payments": [
            {
                "payment_type_id": None,  # 需要从 API 获取支付类型 ID
                "amount": 0  # 会在后面计算
            }
        ],
        "source": "API",
        "note": order_data.get("note", "")
    }
    
    total_amount = 0
    
    # 转换订单项目为收据行项目
    for item in order_data.get("items", []):
        line_item = {
            "item_id": None,  # 需要通过名称查找 ID
            "quantity": item.get("quantity", 1),
            "note": item.get("note", "")
        }
        
        # 这里需要通过菜单数据查找 item_id
        # 暂时使用名称，后续需要实现名称到ID的映射
        line_item["item_name"] = item.get("name", "")
        
        receipt_data["line_items"].append(line_item)
    
    return receipt_data


async def get_payment_types() -> Dict[str, Any]:
    """获取支付类型列表
    
    Returns:
        支付类型数据字典
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{LOYVERSE_API_URL}/payment_types",
                headers=await _get_headers(),
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error("获取支付类型失败，HTTP状态码: %d, 响应: %s", 
                        e.response.status_code, e.response.text)
            raise


# Helper ---------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Normalize item name for comparison.
    1. Lower-case.
    2. Remove accents.
    3. Strip surrounding whitespace.
    4. Remove common punctuation / bracketed text.
    """
    if not name:
        return ""
    # Remove accents
    name = normalize("NFKD", name).encode("ASCII", "ignore").decode("ASCII")
    # Lowercase and strip
    name = name.lower().strip()
    # Remove bracketed content e.g. "(arroz + papas)"
    for sep in ["(", "[", "{" ]:
        if sep in name:
            name = name.split(sep, 1)[0].strip()
    return name


def _find_item_id(name: str, name_to_id: Dict[str, str]) -> Optional[str]:
    """Return exact or fuzzy-matched Loyverse item id for provided name."""
    norm = _normalize_name(name)
    if not norm:
        return None

    # 1) Direct exact match after normalization
    if norm in name_to_id:
        return name_to_id[norm]

    # 2) Fuzzy match using difflib on keys (lower cutoff)
    close = get_close_matches(norm, name_to_id.keys(), n=1, cutoff=0.75)
    if close:
        return name_to_id[close[0]]

    # 3) Token set containment match (order-insensitive)
    tokens = set(norm.split())
    if tokens:
        for key in name_to_id.keys():
            if tokens.issubset(set(key.split())):
                return name_to_id[key]

    # 4) Partial token overlap >= 80 %
    for key in name_to_id.keys():
        key_tokens = set(key.split())
        if key_tokens:
            overlap = len(tokens & key_tokens) / max(len(tokens), 1)
            if overlap >= 0.8:
                return name_to_id[key]

    return None


async def create_order(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """创建订单（收据）
    
    Args:
        order_data: 订单数据字典
        
    Returns:
        包含订单信息的响应字典
        
    Raises:
        httpx.HTTPError: API 请求失败
        ValueError: 订单数据无效
    """
    if not isinstance(order_data, dict):
        raise ValueError("订单数据必须是字典类型")
    
    # 验证必要字段
    if "items" not in order_data or not order_data["items"]:
        raise ValueError("订单必须包含至少一个商品")
    
    logger.debug("创建 Loyverse 收据: %s", json.dumps(order_data, ensure_ascii=False))
    
    try:
        # 确保菜单缓存和索引已构建
        await get_menu_items()
        item_name_to_id = _NAME2ID
        
        # 获取默认支付类型（优先选择现金类型）
        payment_types = await get_payment_types()
        default_payment_type_id = None
        for p in payment_types.get("payment_types", []):
            p_type = p.get("type", "").upper()
            p_name = p.get("name", "").lower()
            if p_type == "CASH" or p_name in {"cash", "efectivo", "кеш", "现金"}:
                default_payment_type_id = p.get("id")
                break
        if not default_payment_type_id and payment_types.get("payment_types"):
            default_payment_type_id = payment_types["payment_types"][0].get("id")
        
        # 构建收据数据
        receipt_data = {
            "store_id": STORE_ID,
            "line_items": [],
            "payments": [],
            "source": "API",
            "note": order_data.get("note", "")
        }
        
        total_amount = 0
        
        # 处理订单项目
        for item in order_data["items"]:
            item_name = item.get("name", "").strip()
            quantity = item.get("quantity", 1)
            
            # 查找商品 ID
            variant_id = _find_item_id(item_name, item_name_to_id)
            if not variant_id:
                logger.warning("未找到商品 '%s' 的 ID，跳过该项目", item_name)
                continue
            
            line_item = {
                "variant_id": variant_id,
                "quantity": quantity
            }
            
            if item.get("note"):
                line_item["note"] = item["note"]
            
            receipt_data["line_items"].append(line_item)
        
        if not receipt_data["line_items"]:
            raise ValueError("没有有效的商品项目可以创建收据")
        
        # 添加默认支付方式（现金）
        if default_payment_type_id:
            receipt_data["payments"] = [{
                "payment_type_id": default_payment_type_id,
                "money_amount": 0  # Loyverse 会自动计算总金额
            }]
        
        # 发送请求创建收据
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{LOYVERSE_API_URL}/receipts",  # 使用正确的端点
                headers=await _get_headers(),
                json=receipt_data,
                timeout=15.0,
            )
            response.raise_for_status()
            
            response_data = response.json()
            
            # 验证响应
            if not isinstance(response_data, dict):
                raise ValueError("API 返回的收据数据格式无效")
            
            receipt_id = response_data.get("id")
            if receipt_id:
                logger.info("收据创建成功 - ID: %s", receipt_id)
            else:
                logger.warning("收据创建成功但未返回 ID")
            
            return response_data
            
    except httpx.HTTPStatusError as e:
        logger.error("创建收据失败，HTTP状态码: %d, 响应: %s", 
                    e.response.status_code, e.response.text)
        # 尝试解析错误详情
        try:
            error_detail = e.response.json()
            logger.error("错误详情: %s", error_detail)
        except:
            pass
        raise
    except httpx.TimeoutException as e:
        logger.error("创建收据超时")
        raise
    except Exception as e:
        logger.error("创建收据时发生未知错误: %s", e)
        raise


async def get_store_info() -> Optional[Dict[str, Any]]:
    """获取商店信息（可选功能，用于验证配置）
    
    Returns:
        商店信息字典，失败时返回 None
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{LOYVERSE_API_URL}/stores/{STORE_ID}",
                headers=await _get_headers(),
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.warning("获取商店信息失败: %s", e)
        return None
