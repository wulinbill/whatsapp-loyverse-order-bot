"""
WhatsApp Loyverse Order Bot - 主应用文件
"""
import asyncio
import time
import json
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .config import get_settings
from .logger import get_logger, business_logger

# 延迟导入，避免循环导入问题
settings = get_settings()
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时的初始化
    logger.info("Starting WhatsApp Ordering Bot...")
    
    try:
        # 动态导入路由和服务
        from .whatsapp.router import whatsapp_router
        from .pos.loyverse_auth import loyverse_auth
        
        # 测试Loyverse连接
        logger.info("Testing Loyverse connection...")
        try:
            loyverse_connected = await loyverse_auth.test_authentication()
            if loyverse_connected:
                logger.info("Loyverse connection successful")
            else:
                logger.warning("Loyverse connection failed - check credentials")
        except Exception as e:
            logger.warning(f"Loyverse connection test failed: {e}")
        
        # 构建向量搜索索引（如果配置了OpenAI）
        if settings.openai_api_key and settings.openai_api_key != "":
            logger.info("Building vector search index...")
            try:
                from .utils.vector_search import vector_search_client
                await vector_search_client.build_embeddings_index()
                logger.info("Vector search index built successfully")
            except Exception as e:
                logger.warning(f"Failed to build vector search index: {e}")
        else:
            logger.info("Vector search disabled - OpenAI API key not configured")
        
        logger.info("Application startup completed")
        
    except Exception as e:
        logger.error(f"Error during startup: {e}")
    
    yield
    
    # 关闭时的清理
    logger.info("Shutting down WhatsApp Ordering Bot...")
    
    try:
        # 清理会话
        from .whatsapp.router import whatsapp_router
        whatsapp_router.cleanup_expired_sessions()
        logger.info("Sessions cleaned up")
    except Exception as e:
        logger.warning(f"Error during cleanup: {e}")
    
    logger.info("Application shutdown completed")

# 创建FastAPI应用
app = FastAPI(
    title="WhatsApp Loyverse Order Bot",
    description="AI-powered WhatsApp ordering system with Loyverse POS integration",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins() if hasattr(settings, 'get_cors_origins') else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志中间件"""
    start_time = time.time()
    
    # 记录请求
    client_ip = request.client.host if request.client else 'unknown'
    logger.info(f"{request.method} {request.url.path} from {client_ip}")
    
    response = await call_next(request)
    
    # 记录响应时间
    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(f"Response {response.status_code} in {duration_ms}ms")
    
    return response

@app.get("/")
async def root():
    """根路径 - 显示应用信息"""
    return {
        "message": "WhatsApp Loyverse Order Bot is running!",
        "status": "healthy",
        "version": "1.0.0",
        "restaurant": settings.restaurant_name,
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "webhook": "/webhook/whatsapp",
            "webhook_alt": "/whatsapp-webhook",
            "admin": "/admin/stats",
            "debug": "/debug/webhook"
        }
    }

@app.get("/health")
async def health_check():
    """健康检查端点"""
    try:
        # 基本健康检查
        health_status = {
            "status": "healthy",
            "timestamp": time.time(),
            "version": "1.0.0",
            "environment": settings.environment
        }
        
        # 检查各个组件的状态
        components = {}
        
        # 检查Loyverse连接
        try:
            from .pos.loyverse_auth import loyverse_auth
            loyverse_healthy = await loyverse_auth.test_authentication()
            components["loyverse"] = "healthy" if loyverse_healthy else "unhealthy"
        except Exception as e:
            components["loyverse"] = "error"
            logger.warning(f"Loyverse health check failed: {e}")
        
        # 检查Claude AI配置
        if settings.anthropic_api_key and settings.anthropic_api_key not in ["", "placeholder"]:
            components["claude_ai"] = "configured"
        else:
            components["claude_ai"] = "not_configured"
        
        # 检查Deepgram配置
        if settings.deepgram_api_key and settings.deepgram_api_key not in ["", "placeholder"]:
            components["speech_to_text"] = "configured"
        else:
            components["speech_to_text"] = "not_configured"
        
        # 检查WhatsApp配置
        if settings.channel_provider == "twilio":
            if settings.twilio_account_sid and settings.twilio_auth_token:
                components["whatsapp"] = "configured"
            else:
                components["whatsapp"] = "not_configured"
        elif settings.channel_provider == "dialog360":
            if hasattr(settings, 'dialog360_token') and settings.dialog360_token:
                components["whatsapp"] = "configured"
            else:
                components["whatsapp"] = "not_configured"
        else:
            components["whatsapp"] = "invalid_provider"
        
        # 检查向量搜索
        if settings.openai_api_key and settings.openai_api_key not in ["", "placeholder"]:
            components["vector_search"] = "configured"
        else:
            components["vector_search"] = "not_configured"
        
        health_status["components"] = components
        
        # 如果关键组件不健康，返回503
        critical_components = ["loyverse", "claude_ai", "whatsapp"]
        unhealthy_critical = [
            comp for comp in critical_components 
            if components.get(comp) in ["unhealthy", "error", "not_configured", "invalid_provider"]
        ]
        
        if unhealthy_critical:
            health_status["status"] = "degraded"
            health_status["issues"] = unhealthy_critical
            if "loyverse" in unhealthy_critical:
                return JSONResponse(content=health_status, status_code=503)
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            content={
                "status": "error", 
                "error": str(e),
                "timestamp": time.time()
            },
            status_code=500
        )

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """WhatsApp webhook端点 - 支持多种数据格式"""
    try:
        # 获取 Content-Type
        content_type = request.headers.get("content-type", "").lower()
        logger.info(f"Webhook Content-Type: {content_type}")
        
        payload = {}
        
        if "application/json" in content_type:
            # JSON 格式（360Dialog 等）
            try:
                payload = await request.json()
                logger.info("Parsed JSON payload")
            except Exception as e:
                logger.error(f"Failed to parse JSON: {e}")
                raise HTTPException(status_code=400, detail="Invalid JSON payload")
                
        elif "application/x-www-form-urlencoded" in content_type:
            # 表单格式（Twilio）
            try:
                form_data = await request.form()
                payload = dict(form_data)
                logger.info(f"Parsed form payload with {len(payload)} fields")
                
                # 记录主要字段（用于调试）
                key_fields = ["From", "To", "Body", "MessageSid", "AccountSid", "MediaUrl0", "MediaContentType0"]
                debug_info = {}
                for field in key_fields:
                    if field in payload:
                        debug_info[field] = payload[field]
                
                if debug_info:
                    logger.info(f"Form data fields: {debug_info}")
                        
            except Exception as e:
                logger.error(f"Failed to parse form data: {e}")
                raise HTTPException(status_code=400, detail="Invalid form data")
        else:
            # 尝试获取原始数据并自动检测格式
            try:
                body = await request.body()
                logger.info(f"Raw body length: {len(body)}")
                
                if not body:
                    logger.warning("Empty request body")
                    return JSONResponse(content={"status": "accepted", "message": "empty_body"}, status_code=200)
                
                body_str = body.decode('utf-8')
                logger.info(f"Raw body preview: {body_str[:200]}")
                
                # 尝试解析为 JSON
                try:
                    payload = json.loads(body_str)
                    logger.info("Successfully parsed raw body as JSON")
                except json.JSONDecodeError:
                    # 如果不是 JSON，尝试解析为表单数据
                    try:
                        from urllib.parse import parse_qs
                        parsed = parse_qs(body_str)
                        # 将列表值转换为单个值
                        payload = {k: v[0] if v else '' for k, v in parsed.items()}
                        logger.info("Successfully parsed raw body as form data")
                    except Exception as e:
                        logger.error(f"Failed to parse raw body: {e}")
                        raise HTTPException(status_code=400, detail="Unable to parse request body")
                        
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error processing request body: {e}")
                raise HTTPException(status_code=400, detail="Request processing error")
        
        # 验证 payload
        if not isinstance(payload, dict):
            logger.error(f"Payload is not a dictionary, got: {type(payload)}")
            raise HTTPException(status_code=400, detail="Invalid payload format")
        
        if not payload:
            logger.warning("Received empty payload")
            return JSONResponse(content={"status": "accepted", "message": "empty_payload"}, status_code=200)
        
        # 记录 webhook 接收
        user_agent = request.headers.get('user-agent', 'unknown')
        logger.info(f"Received WhatsApp webhook from: {user_agent}")
        
        # 验证 webhook 签名（根据提供商）
        if settings.channel_provider == "twilio":
            # TODO: 实现 Twilio 签名验证
            logger.info("Twilio webhook received (signature validation skipped)")
        elif settings.channel_provider == "dialog360":
            # TODO: 实现 360Dialog 签名验证
            logger.info("360Dialog webhook received")
        
        # 在后台处理消息（避免阻塞 webhook 响应）
        background_tasks.add_task(process_webhook_message, payload)
        
        # 立即返回 200 响应
        return JSONResponse(content={"status": "accepted"}, status_code=200)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        business_logger.log_error(
            user_id="webhook",
            stage="inbound",
            error_code="WEBHOOK_ERROR",
            error_msg=str(e),
            exception=e
        )
        
        # 仍然返回 200 以避免 webhook 重试
        return JSONResponse(
            content={"status": "error", "error": "internal_error"}, 
            status_code=200
        )

async def process_webhook_message(payload: Dict[str, Any]):
    """后台处理webhook消息"""
    try:
        from .whatsapp.router import whatsapp_router
        
        # 记录收到的数据类型和关键信息
        logger.info(f"Processing webhook payload with keys: {list(payload.keys())}")
        
        # 检测并标准化不同提供商的数据格式
        if "From" in payload and "Body" in payload:
            # Twilio 格式
            logger.info("Detected Twilio webhook format")
            payload["provider"] = "twilio"
            
            # 记录关键信息
            from_number = payload.get("From", "")
            message_body = payload.get("Body", "")
            message_sid = payload.get("MessageSid", "")
            
            logger.info(f"Twilio message - From: {from_number}, Body: {message_body[:50]}..., SID: {message_sid}")
            
        elif "messages" in payload or "contacts" in payload:
            # 360Dialog 格式
            logger.info("Detected 360Dialog webhook format")  
            payload["provider"] = "dialog360"
        else:
            logger.info("Unknown webhook format, proceeding with raw data")
            payload["provider"] = "unknown"
        
        # 处理消息
        result = await whatsapp_router.handle_incoming_message(payload)
        
        status = result.get('status', 'unknown') if isinstance(result, dict) else 'processed'
        logger.info(f"Message processed: {status}")
        
    except Exception as e:
        logger.error(f"Background message processing error: {e}", exc_info=True)
        
        # 从payload中提取用户信息
        from_number = "unknown"
        if isinstance(payload, dict):
            # Twilio格式
            from_number = payload.get("From", payload.get("from_number", "unknown"))
            # 去掉 whatsapp: 前缀（如果存在）
            if from_number.startswith("whatsapp:"):
                from_number = from_number[9:]
        
        business_logger.log_error(
            user_id=from_number,
            stage="processing",
            error_code="BACKGROUND_PROCESS_ERROR",
            error_msg=str(e),
            exception=e
        )

@app.get("/webhook/whatsapp")
async def whatsapp_webhook_verification(request: Request):
    """WhatsApp webhook验证端点（用于某些提供商的验证流程）"""
    try:
        # 获取查询参数
        hub_mode = request.query_params.get("hub.mode")
        hub_verify_token = request.query_params.get("hub.verify_token")
        hub_challenge = request.query_params.get("hub.challenge")
        
        logger.info(f"Webhook verification request: mode={hub_mode}, token={hub_verify_token}")
        
        # 简单的验证逻辑（在生产环境中应该使用更安全的验证）
        expected_token = "whatsapp_verify_token"  # 应该从环境变量获取
        
        if hub_mode == "subscribe" and hub_verify_token == expected_token:
            logger.info("Webhook verification successful")
            return int(hub_challenge) if hub_challenge else "verified"
        else:
            logger.warning(f"Webhook verification failed: mode={hub_mode}, token={hub_verify_token}")
            raise HTTPException(status_code=403, detail="Verification failed")
            
    except ValueError:
        logger.error("Invalid challenge value")
        raise HTTPException(status_code=400, detail="Invalid challenge")
    except Exception as e:
        logger.error(f"Webhook verification error: {e}")
        raise HTTPException(status_code=500, detail="Verification error")

# ==============================================================================
# 兼容性别名路由
# ==============================================================================

@app.post("/whatsapp-webhook")
async def twilio_whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """Twilio WhatsApp webhook端点（别名路由）"""
    logger.info("Received webhook via Twilio-style URL (/whatsapp-webhook)")
    return await whatsapp_webhook(request, background_tasks)

@app.get("/whatsapp-webhook")
async def twilio_whatsapp_webhook_verification(request: Request):
    """Twilio WhatsApp webhook验证端点（别名路由）"""
    logger.info("Received webhook verification via Twilio-style URL")
    return await whatsapp_webhook_verification(request)

@app.post("/twilio/webhook")
async def twilio_webhook_alt(request: Request, background_tasks: BackgroundTasks):
    """Twilio webhook备用端点"""
    logger.info("Received webhook via /twilio/webhook")
    return await whatsapp_webhook(request, background_tasks)

@app.get("/twilio/webhook")
async def twilio_webhook_verification_alt(request: Request):
    """Twilio webhook验证备用端点"""
    logger.info("Received webhook verification via /twilio/webhook")
    return await whatsapp_webhook_verification(request)

# ==============================================================================
# 调试端点
# ==============================================================================

@app.post("/debug/webhook")
async def debug_webhook(request: Request):
    """调试 webhook 数据格式"""
    try:
        # 获取所有信息
        headers = dict(request.headers)
        content_type = headers.get("content-type", "")
        
        # 获取原始数据
        body = await request.body()
        
        debug_info = {
            "headers": headers,
            "content_type": content_type,
            "body_length": len(body),
            "body_raw": body.decode('utf-8') if body else "",
            "query_params": dict(request.query_params)
        }
        
        # 尝试解析数据
        if "application/json" in content_type:
            try:
                # 重新创建 request 来解析 JSON（因为 body 已经被读取）
                json_data = json.loads(body.decode('utf-8'))
                debug_info["parsed_json"] = json_data
            except:
                debug_info["json_parse_error"] = "Failed to parse JSON"
        
        if "application/x-www-form-urlencoded" in content_type:
            try:
                from urllib.parse import parse_qs
                parsed = parse_qs(body.decode('utf-8'))
                debug_info["parsed_form"] = {k: v[0] if v else '' for k, v in parsed.items()}
            except:
                debug_info["form_parse_error"] = "Failed to parse form"
        
        logger.info(f"Debug webhook info: {debug_info}")
        
        return debug_info
        
    except Exception as e:
        logger.error(f"Debug webhook error: {e}")
        return {"error": str(e)}

# ==============================================================================
# 管理端点
# ==============================================================================

@app.post("/admin/cleanup-sessions")
async def cleanup_sessions():
    """管理端点：清理过期会话"""
    try:
        from .whatsapp.router import whatsapp_router
        
        initial_count = len(whatsapp_router.user_sessions)
        whatsapp_router.cleanup_expired_sessions()
        final_count = len(whatsapp_router.user_sessions)
        
        cleaned_count = initial_count - final_count
        
        return {
            "status": "success",
            "sessions_cleaned": cleaned_count,
            "remaining_sessions": final_count,
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"Session cleanup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/rebuild-index")
async def rebuild_vector_index():
    """管理端点：重建向量搜索索引"""
    try:
        if not settings.openai_api_key or settings.openai_api_key in ["", "placeholder"]:
            raise HTTPException(status_code=400, detail="OpenAI API key not configured")
        
        from .utils.vector_search import vector_search_client
        await vector_search_client.build_embeddings_index()
        
        return {
            "status": "success", 
            "message": "Vector index rebuilt successfully",
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"Index rebuild error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/stats")
async def get_stats():
    """管理端点：获取统计信息"""
    try:
        from .whatsapp.router import whatsapp_router
        from .pos.loyverse_auth import loyverse_auth
        
        stats = {
            "timestamp": time.time(),
            "active_sessions": len(whatsapp_router.user_sessions),
            "provider": settings.channel_provider,
            "environment": settings.environment,
            "restaurant": settings.restaurant_name,
            "components": {
                "loyverse_token_valid": loyverse_auth.get_token_info().get("valid", False) if hasattr(loyverse_auth, 'get_token_info') else "unknown",
                "ai_configured": bool(settings.anthropic_api_key and settings.anthropic_api_key != "placeholder"),
                "speech_configured": bool(settings.deepgram_api_key and settings.deepgram_api_key != "placeholder"),
                "vector_search_configured": bool(settings.openai_api_key and settings.openai_api_key != "placeholder")
            }
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/config")
async def get_config():
    """管理端点：获取非敏感配置信息"""
    try:
        config_info = {
            "restaurant_name": settings.restaurant_name,
            "environment": settings.environment,
            "channel_provider": settings.channel_provider,
            "tax_rate": settings.tax_rate,
            "preparation_times": {
                "basic": settings.preparation_time_basic,
                "complex": settings.preparation_time_complex
            },
            "ai_settings": {
                "model": settings.anthropic_model,
                "fuzzy_threshold": settings.fuzzy_match_threshold,
                "vector_threshold": getattr(settings, 'vector_search_threshold', 0.7)
            },
            "features": {
                "voice_enabled": bool(settings.deepgram_api_key and settings.deepgram_api_key != "placeholder"),
                "vector_search_enabled": bool(settings.openai_api_key and settings.openai_api_key != "placeholder"),
                "analytics_enabled": getattr(settings, 'enable_analytics', True)
            }
        }
        
        return config_info
        
    except Exception as e:
        logger.error(f"Config endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# 异常处理
# ==============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    business_logger.log_error(
        user_id="system",
        stage="global",
        error_code="UNHANDLED_EXCEPTION",
        error_msg=str(exc),
        exception=exc
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "timestamp": time.time(),
            "request_path": str(request.url.path)
        }
    )

# ==============================================================================
# 应用启动
# ==============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=(settings.environment == "development"),
        access_log=True
    )
