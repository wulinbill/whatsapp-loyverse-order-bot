"""Loyverse POS API 封装模块  – 2025‑06 修正版
-------------------------------------------------
✓ 线程安全的菜单缓存（asyncio.Lock）
✓ 别名规则追加：mini combo… & “mini combinación de …” 等
✓ 收据 ID 回退：id → receipt_uuid → headers['Location']
✓ 允许 Cash / Efectivo 自动匹配失败时使用首个 payment_type
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional
from unicodedata import normalize
from difflib import get_close_matches

import httpx

from loyverse_auth import get_access_token
from utils.logger import get_logger

logger = get_logger(__name__)

LOYVERSE_API_URL = "https://api.loyverse.com/v1.0"
STORE_ID = os.getenv("LOYVERSE_STORE_ID")
if not STORE_ID:
    raise RuntimeError("Environment variable LOYVERSE_STORE_ID is required but missing.")

# ---------------------------------------------------------------------------
# In‑memory menu cache & name→id index (thread‑safe)
# ---------------------------------------------------------------------------
_MENU_CACHE: Optional[Dict[str, Any]] = None  # raw json from API
_NAME2ID: Dict[str, str] = {}
_CACHE_TS: float = 0.0
CACHE_TTL = int(os.getenv("LOYVERSE_MENU_CACHE_TTL", "600"))  # default 10 min

# ⚡ NEW: async lock to avoid duplicated upstream calls when many coroutines
_MENU_LOCK = asyncio.Lock()


def get_name_to_id_mapping() -> Dict[str, str]:
    """Public, read‑only view for other modules."""
    return _NAME2ID

# historic import alias
name2id = _NAME2ID

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

async def _get_headers() -> Dict[str, str]:
    token = await get_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

# ---------------------------------------------------------------------------
# Menu download / cache ------------------------------------------------------
# ---------------------------------------------------------------------------

async def get_menu_items(cache_path: str = "menu_data.json", force_refresh: bool = False) -> Dict[str, Any]:
    """Return menu json, using memory+disk cache.
    Lock protected so only the first coroutine hits the API.
    """
    global _MENU_CACHE, _NAME2ID, _CACHE_TS

    async with _MENU_LOCK:
        # still fresh? ----------------------------------------------
        if _MENU_CACHE and not force_refresh and (time.time() - _CACHE_TS < CACHE_TTL):
            logger.debug("使用内存缓存的菜单 (age %.1fs)", time.time() - _CACHE_TS)
            return _MENU_CACHE

        cache_file = Path(cache_path)
        if not force_refresh and cache_file.exists():
            try:
                _MENU_CACHE = json.loads(cache_file.read_text("utf‑8"))
                _CACHE_TS = time.time()
                logger.debug("从磁盘缓存加载菜单 – %d 个项目", len(_MENU_CACHE.get("items", [])))
            except Exception as exc:
                logger.warning("缓存文件读取失败: %s，将从 API 重新获取", exc)
                _MENU_CACHE = None

        if _MENU_CACHE and not force_refresh:
            if not _NAME2ID:
                _build_name_index(_MENU_CACHE)
            return _MENU_CACHE

        # ----- hit API ------------------------------------------------------
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{LOYVERSE_API_URL}/items", headers=await _get_headers(),
                    params={"limit": 250, "deleted": False}, timeout=15.0,
                )
                resp.raise_for_status()
            except httpx.TimeoutException:
                logger.error("获取菜单超时")
                raise
            except httpx.HTTPStatusError as exc:
                logger.error("获取菜单失败，HTTP %d – %s", exc.response.status_code, exc.response.text)
                raise

        data: Dict[str, Any] = resp.json()
        if "items" not in data:
            raise ValueError("API 返回的菜单数据格式无效")

        _MENU_CACHE, _CACHE_TS = data, time.time()
        _build_name_index(data)

        try:
            cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf‑8")
            logger.info("菜单已缓存到磁盘 – %d 个项目", len(data.get("items", [])))
        except IOError as exc:
            logger.warning("无法保存菜单缓存: %s", exc)

        return data

# ---------------------------------------------------------------------------
# Index builder --------------------------------------------------------------
# ---------------------------------------------------------------------------

def _build_name_index(menu_data: Dict[str, Any]) -> None:
    """(re)Generate `_NAME2ID` mapping."""
    _NAME2ID.clear()

    for itm in menu_data.get("items", []):
        base_key = _normalize_name(itm.get("name", ""))
        variants = itm.get("variants", []) or []

        # ---------------- Extra aliases ----------------------------------
        raw = itm.get("name", "")
        extra: list[str] = []

        # 1️⃣ strip leading "Combinacion… / Combinación …" (accent optional)
        m = re.match(r"(?i)\s*combinaci(?:o?n|ones)?\s+(.*)", raw)
        if m:
            body = m.group(1).strip()
            extra += [body, f"mini {body}",
                      f"mini combinacion {body}", f"mini combinación {body}",
                      f"combinacion de {body}", f"combinación de {body}"]

        # 2️⃣ remove default side‑dish tails
        out = re.sub(r"\([^)]+\)", "", raw)
        out = re.sub(r"(?i)\s*arroz\s*\+\s*(papa frita|tostones?|ensalada|papas)\s*", "", out).strip()
        if out and out != raw:
            extra.append(out)

        # 3️⃣ items starting with "Cambio …" → drop prefix
        if raw.lower().startswith("cambio"):
            extra.append(raw[6:].strip())

        # Normalize extra aliases
        extra = [_normalize_name(x) for x in extra if x]
        # ----------------------------------------------------------------

        def _vid(obj: Dict[str, Any]):
            return obj.get("id") or obj.get("variant_id")

        if base_key:
            _NAME2ID[base_key] = _vid(variants[0]) if variants else itm.get("id")

        for var in variants:
            vname = var.get("name") or var.get("variant_name") or ""
            if not vname:
                continue
            _NAME2ID[_normalize_name(f"{raw} {vname}")] = _vid(var)

        mid = _vid(variants[0]) if variants else itm.get("id")
        for alias in extra:
            _NAME2ID[alias] = mid

        # alias: extract from description "Alias: xxx, yyy"
        desc = itm.get("description") or ""
        if desc:
            desc_plain = re.sub(r"<[^>]+>", " ", desc)
            m2 = re.search(r"alias[:：]\s*(.*)", desc_plain, re.I)
            if m2:
                for a in re.split(r"[,，/；;]", m2.group(1)):
                    a = _normalize_name(a)
                    if a:
                        _NAME2ID[a] = mid

    logger.debug("已建立 name→id 索引，共 %d 项", len(_NAME2ID))

# ---------------------------------------------------------------------------
# Normalisation & fuzzy match ------------------------------------------------
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    if not name:
        return ""
    name = normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.lower().strip()
    for sep in ("(", "[", "{"):
        if sep in name:
            name = name.split(sep, 1)[0].strip()
    for p in ("-", "/", "+", "&", ":", ";", ",", "–", "—"):
        name = name.replace(p, " ")
    while "  " in name:
        name = name.replace("  ", " ")
    return name


def _find_item_id(name: str, mapping: Dict[str, str]) -> Optional[str]:
    norm = _normalize_name(name)
    if not norm:
        return None
    if norm in mapping:
        return mapping[norm]
    close = get_close_matches(norm, mapping.keys(), n=1, cutoff=0.75)
    if close:
        return mapping[close[0]]
    tokens = set(norm.split())
    for k, v in mapping.items():
        kt = set(k.split())
        if tokens and tokens.issubset(kt):
            return v
        if kt and len(tokens & kt) / max(len(tokens), 1) >= 0.8:
            return v
    return None

# ---------------------------------------------------------------------------
# Payment types --------------------------------------------------------------
# ---------------------------------------------------------------------------

async def get_payment_types() -> Dict[str, Any]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{LOYVERSE_API_URL}/payment_types", headers=await _get_headers(), timeout=10.0)
        resp.raise_for_status()
        return resp.json()

# ---------------------------------------------------------------------------
# Order / receipt creation ---------------------------------------------------
# ---------------------------------------------------------------------------

async def create_order(order: Dict[str, Any]) -> Dict[str, Any]:
    if not (isinstance(order, dict) and order.get("items")):
        raise ValueError("订单必须包含至少一个商品")

    await get_menu_items()  # ensure cache ready
    mapping = _NAME2ID

    # ---- default payment type (cash) -----------------------------------
    cash_id: Optional[str] = None
    try:
        for p in (await get_payment_types()).get("payment_types", []):
            if p.get("type", "").upper() == "CASH" or p.get("name", "").lower() in {"cash", "efectivo", "现金"}:
                cash_id = p.get("id"); break
        if not cash_id:
            cash_id = (await get_payment_types())["payment_types"][0]["id"]
    except Exception as exc:
        logger.warning("支付类型获取失败，将不写 payments: %s", exc)

    receipt: Dict[str, Any] = {
        "store_id": STORE_ID,
        "line_items": [],
        "payments": [],
        "source": "API",
        "note": order.get("note", ""),
    }

    for it in order["items"]:
        vid = _find_item_id(it.get("name", ""), mapping)
        if not vid:
            logger.warning("未找到商品 '%s' 的 ID，跳过", it.get("name"))
            continue
        li = {"variant_id": vid, "quantity": it.get("quantity", 1)}
        if it.get("note"):
            li["note"] = it["note"]
        receipt["line_items"].append(li)

    if not receipt["line_items"]:
        raise ValueError("没有有效的商品项目可以创建收据")

    if cash_id:
        receipt["payments"] = [{"payment_type_id": cash_id, "money_amount": 0}]

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{LOYVERSE_API_URL}/receipts", headers=await _get_headers(), json=receipt, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()

    # -------- fallback receipt id retrieval --------------------------------
    rid = data.get("id") or data.get("receipt_uuid")
    if not rid:
        loc = resp.headers.get("Location", "")
        m = re.search(r"/receipts/([A-Za-z0-9-]+)", loc)
        rid = m.group(1) if m else None
    if rid:
        logger.info("收据创建成功 – ID: %s", rid)
    else:
        logger.warning("收据创建成功但未返回 ID")

    return data

# ---------------------------------------------------------------------------
# Convenience helpers -------------------------------------------------------
# ---------------------------------------------------------------------------

async def create_customer(name: str, phone: str = "") -> Optional[str]:
    payload = {"name": name.strip()}
    if phone:
        payload["phone"] = phone.strip()
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{LOYVERSE_API_URL}/customers", headers=await _get_headers(), json=payload, timeout=10.0)
            r.raise_for_status(); d = r.json(); return d.get("id") or d.get("customer_id")
    except Exception as exc:
        logger.warning("创建顾客失败: %s", exc)
        return None


async def get_store_info() -> Optional[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{LOYVERSE_API_URL}/stores/{STORE_ID}", headers=await _get_headers(), timeout=10.0)
            r.raise_for_status(); return r.json()
    except Exception as exc:
        logger.warning("获取商店信息失败: %s", exc)
        return None
