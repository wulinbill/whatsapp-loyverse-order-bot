import os, json, difflib, unicodedata
from typing import List, Dict
import loyverse_api

KB_PATH = os.path.join(os.path.dirname(__file__), "data", "menu_kb.json")
MENU = json.load(open(KB_PATH, encoding="utf-8"))

def _norm(t): return unicodedata.normalize('NFD', t.casefold()).encode('ascii','ignore').decode()

def search_menu(q: str, k=3) -> List[Dict]:
    norm_q = _norm(q)
    names = [_norm(m["name"]) for m in MENU]
    hits = difflib.get_close_matches(norm_q, names, n=k, cutoff=0.4)
    return [m for m in MENU if _norm(m["name"]) in hits][:k]

def place_loyverse_order(items: List[Dict]) -> str:
    payload = {"register_id": os.getenv("LOYVERSE_REGISTER_ID", ""), "line_items": items}
    res = loyverse_api.place_order(payload)
    return res.get("receipt_number", "unknown")
