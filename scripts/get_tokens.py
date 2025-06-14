"""命令行脚本：用 OAuth 授权 Code 换取 Access/Refresh Token"""
import argparse, httpx, json

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--code")
    p.add_argument("--client_id")
    p.add_argument("--client_secret")
    args = p.parse_args()

    resp = httpx.post(
        "https://api.loyverse.com/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": args.code,
            "client_id": args.client_id,
            "client_secret": args.client_secret
        }, timeout=15
    )
    resp.raise_for_status()
    print(json.dumps(resp.json(), indent=2))

if __name__ == "__main__":
    main()
