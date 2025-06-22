import re
from typing import List, Dict
from tools import search_menu

def convert(sentences: List[str]) -> List[Dict]:
    out=[]
    for s in sentences:
        m = re.match(r"(\d+)\s+", s.strip())
        qty = int(m.group(1)) if m else 1
        name = s[m.end():] if m else s
        cand = search_menu(name,1)
        if cand:
            item=cand[0]
            out.append({"variant_id":item["variant_id"],"quantity":qty,"price":item["price"]})
    return out
