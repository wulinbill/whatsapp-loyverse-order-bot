import os, json, time, httpx, pathlib

TOKEN_FILE = pathlib.Path("/mnt/data/loyverse_token.json")

def _save(tok):
    TOKEN_FILE.write_text(json.dumps(tok))

def _load():
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return {}

def refresh_access_token():
    refresh_token = os.getenv("LOYVERSE_REFRESH_TOKEN") or _load().get("refresh_token")
    if not refresh_token:
        raise RuntimeError("No refresh token")
    r = httpx.post("https://api.loyverse.com/oauth/token", data={
        "grant_type":"refresh_token",
        "refresh_token":refresh_token,
        "client_id":os.getenv("LOYVERSE_CLIENT_ID"),
        "client_secret":os.getenv("LOYVERSE_CLIENT_SECRET")
    }, timeout=15)
    r.raise_for_status()
    tok = r.json()
    tok["expires_at"] = int(time.time()) + tok.get("expires_in", 3500)
    _save(tok)
    return tok["access_token"]

def get_access_token():
    tok = _load()
    if tok and tok.get("expires_at",0) -60 > time.time():
        return tok["access_token"]
    return refresh_access_token()
