"""命令行脚本：使用 OAuth 授权码换取 Access/Refresh Token"""
import argparse
import json
import sys
from typing import Optional, Dict, Any
import httpx


def get_tokens(code: str, client_id: str, client_secret: str, 
               redirect_uri: Optional[str] = None) -> Dict[str, Any]:
    """使用授权码获取访问令牌
    
    Args:
        code: OAuth 授权码
        client_id: Loyverse 客户端 ID
        client_secret: Loyverse 客户端密钥
        redirect_uri: 可选的重定向 URI
        
    Returns:
        包含令牌信息的字典
        
    Raises:
        httpx.HTTPError: HTTP 请求失败
        ValueError: 参数无效
    """
    if not all([code, client_id, client_secret]):
        raise ValueError("code, client_id 和 client_secret 都是必需的参数")
    
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret
    }
    
    if redirect_uri:
        payload["redirect_uri"] = redirect_uri
    
    try:
        with httpx.Client() as client:
            response = client.post(
                "https://api.loyverse.com/oauth/token",
                data=payload,
                timeout=15.0
            )
            response.raise_for_status()
            return response.json()
            
    except httpx.HTTPStatusError as e:
        print(f"错误: HTTP {e.response.status_code}")
        print(f"响应内容: {e.response.text}")
        raise
    except httpx.TimeoutException:
        print("错误: 请求超时")
        raise
    except Exception as e:
        print(f"意外错误: {e}")
        raise


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="使用 OAuth 授权码获取 Loyverse API 令牌",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python get_tokens.py --code YOUR_AUTH_CODE --client_id YOUR_CLIENT_ID --client_secret YOUR_CLIENT_SECRET

获取授权码的步骤:
  1. 访问 Loyverse 开发者控制台
  2. 创建应用并获取 client_id 和 client_secret
  3. 构建授权 URL 并获取授权码
  4. 使用此脚本获取访问令牌
        """
    )
    
    parser.add_argument(
        "--code", 
        required=True,
        help="OAuth 授权码"
    )
    parser.add_argument(
        "--client_id", 
        required=True,
        help="Loyverse 应用的客户端 ID"
    )
    parser.add_argument(
        "--client_secret", 
        required=True,
        help="Loyverse 应用的客户端密钥"
    )
    parser.add_argument(
        "--redirect_uri",
        help="可选的重定向 URI（如果在授权时使用了）"
    )
    parser.add_argument(
        "--output",
        help="输出文件路径（如果不指定则输出到控制台）"
    )
    
    args = parser.parse_args()
    
    try:
        print("正在获取访问令牌...")
        token_data = get_tokens(
            args.code,
            args.client_id, 
            args.client_secret,
            args.redirect_uri
        )
        
     diff --git a/scripts/get_tokens.py b/scripts/get_tokens.py
index 1191639ecdd6b11805dcb5a7d0cf0061bb90954d..737bb702b540acd6c1bede2a57e93b9c1f2ea47f 100644
--- a/scripts/get_tokens.py
+++ b/scripts/get_tokens.py
@@ -88,26 +88,42 @@ def main():
     parser.add_argument(
         "--client_secret", 
         required=True,
         help="Loyverse 应用的客户端密钥"
     )
     parser.add_argument(
         "--redirect_uri",
         help="可选的重定向 URI（如果在授权时使用了）"
     )
     parser.add_argument(
         "--output",
         help="输出文件路径（如果不指定则输出到控制台）"
     )
     
     args = parser.parse_args()
     
     try:
         print("正在获取访问令牌...")
         token_data = get_tokens(
             args.code,
             args.client_id, 
             args.client_secret,
             args.redirect_uri
         )
+        # 格式化输出并显示结果
+        token_json = json.dumps(token_data, ensure_ascii=False, indent=2)
+        if args.output:
+            with open(args.output, "w", encoding="utf-8") as f:
+                f.write(token_json)
+            print(f"令牌已写入 {args.output}")
+        else:
+            print("获取到的令牌信息:")
+            print(token_json)
+
+    except Exception as e:
+        print(f"获取令牌失败: {e}")
+        sys.exit(1)
+
+
+if __name__ == "__main__":
+    main()

