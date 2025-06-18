from __future__ import annotations
import time
from typing import Dict, Any

# Simple in-memory session dict; consider replacing with Redis in prod
_SESSIONS: Dict[str, Dict[str, Any]] = {}
TTL = 60 * 60  # 1 hour


def get_session(user_id: str) -> Dict[str, Any]:
    sess = _SESSIONS.get(user_id)
    now = time.time()
    if sess and now - sess.get("_ts", now) > TTL:
        # expired
        sess = None
    if not sess:
        sess = {
            "stage": "GREETING",
            "items": [],
            "customer_id": None,
            "name": None,
            "_ts": now,
        }
        _SESSIONS[user_id] = sess
    else:
        sess["_ts"] = now  # refresh timestamp
    return sess


def reset_session(user_id: str):
    _SESSIONS.pop(user_id, None) 