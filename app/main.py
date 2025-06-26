import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .config import get_settings
from .logger import get_logger, business_logger
from .whatsapp.router import whatsapp_router
from .pos.loyverse_auth import loyverse_auth
from .utils.vector_search import vector_search_client

settings = get_settings()
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时的初始化
    logger.info("Starting WhatsApp Ordering Bot...")
    
    try:
        # 测试Loyverse连接
        logger.info("Testing Loyverse connection...")
        loyverse_connected = await loyverse_auth.test_authentication()
        if loyverse_connected:
            logger.info("Loyverse connection successful")
        else:
            logger.warning("Loyverse connection failed")
        
        # 构建向量搜索索引（如果配置了OpenAI）
        if settings.openai_api_key:
            logger.info("Building vector search index...")
            try:
                await vector_search_client.build_embeddings_index()
                logger.info("Vector search index built successfully")
            except Exception as e:
                logger.warning(f"Failed to build vector search index: {e}")
        
        logger.info("Application startup completed")
        
    except Exception as e:
        logger.error(f"Error during startup: {e}")
    
    yield
    
    # 关闭时的清理
    logger.info("Shutting down WhatsApp Ordering Bot...")
    
    # 清理会话
    whatsapp_router.cleanup_expired_sessions()
    
    logger.info("Application shutdown completed")

# 创建FastAPI应用
app = FastAPI(
    title="WhatsApp Ordering Bot",
    description="多语言WhatsApp订餐机器人，基于Claude AI和Loyverse POS",
    version="1.0.0",
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志中间件"""
    start_time = time.time()
    
    # 记录请求
    logger.info(f"{request.method} {request.url.path} from {request.client.host if request.client else 'unknown'}")
    
    response = await call_next(request)
    
    # 记录响应时间
    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(f"Response {response.status_code} in {duration_ms}ms")
    
    return response

@app.get("/health")
async def health_check():
    """健康检查端点"""
    try:
        # 基本健康检查
        health_status = {
            "status": "healthy",
            "timestamp": time.time(),
            "version": "1.0.0"
        }
        
        # 检查各个组件的状态
        components = {}
        
        # 检查Loyverse连接
        try:
            loyverse_healthy = await loyverse_auth.test_authentication()
            components["loyverse"] = "healthy" if loyverse_healthy else "unhealthy"
        except Exception as e:
            components["loyverse"] = "unhealthy"
            logger.warning(f"Loyverse health check failed: {e}")
        
        # 检查Claude API（通过检查配置）
        components["claude"] = "healthy" if settings.anthropic_api_key else "not_configured"
        
        # 检查Deepgram API
        components["deepgram"] = "healthy" if settings.deepgram_api_key else "not_configured"
        
        # 检查WhatsApp适配器
        if settings.channel_provider == "twilio":
            components["whatsapp"] = "healthy" if (settings.twilio_account_sid and settings.twilio_auth_token) else "not_configured"
        else:
            components["whatsapp"] = "healthy" if settings.dialog360_token else "not_configured"
        
        health_status["components"] = components
        
        # 如果关键组件不健康，返回503
        critical_components = ["loyverse", "claude", "whatsapp"]
        unhealthy_critical = [comp for comp in critical_components if components.get(comp) == "unhealthy"]
        
        if unhealthy_critical:
            health_status["status"] = "unhealthy"
            health_status["unhealthy_components"] = unhealthy_critical
            return JSONResponse(content=health_status, status_code=503)
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            content={"status": "error", "error": str(e)},
            status_code=500
        )

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """WhatsApp webhook端点"""
    try:
        # 获取原始请求体
        body = await request.body()
        
        # 解析JSON
        try:
            payload = await request.json()
        except Exception as e:
            logger.error(f"Failed to parse webhook JSON: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
        # 记录webhook接收
        logger.info(f"Received WhatsApp webhook: {request.headers.get('user-agent', 'unknown')}")
        
        # 验证webhook（这里可以添加签名验证）
        if settings.channel_provider == "twilio":
            # Twilio webhook验证逻辑
            pass
        elif settings.channel_provider == "dialog360":
            # 360Dialog webhook验证逻辑
            pass
        
        # 在后台处理消息（避免阻塞webhook响应）
        background_tasks.add_task(process_webhook_message, payload)
        
        # 立即返回200响应
        return JSONResponse(content={"status": "accepted"}, status_code=200)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        business_logger.log_error(
            user_id="webhook",
            stage="inbound",
            error_code="WEBHOOK_ERROR",
            error_msg=str(e),
            exception=e
        )
        
        # 仍然返回200以避免webhook重试
        return JSONResponse(content={"status": "error", "error": "internal_error"}, status_code=200)

async def process_webhook_message(payload: Dict[str, Any]):
    """后台处理webhook消息"""
    try:
        result = await whatsapp_router.handle_incoming_message(payload)
        logger.info(f"Message processed: {result.get('status', 'unknown')}")
        
    except Exception as e:
        logger.error(f"Background message processing error: {e}")
        business_logger.log_error(
            user_id=payload.get("from_number", "unknown"),
            stage="processing",
            error_code="BACKGROUND_PROCESS_ERROR",
            error_msg=str(e),
            exception=e
        )

@app.get("/webhook/whatsapp")
async def whatsapp_webhook_verification(request: Request):
    """WhatsApp webhook验证端点（用于Twilio等）"""
    try:
        # Twilio webhook验证
        hub_mode = request.query_params.get("hub.mode")
        hub_verify_token = request.query_params.get("hub.verify_token")
        hub_challenge = request.query_params.get("hub.challenge")
        
        if hub_mode == "subscribe" and hub_verify_token == "your_verify_token":
            logger.info("Webhook verification successful")
            return int(hub_challenge)
        else:
            logger.warning("Webhook verification failed")
            raise HTTPException(status_code=403, detail="Verification failed")
            
    except Exception as e:
        logger.error(f"Webhook verification error: {e}")
        raise HTTPException(status_code=500, detail="Verification error")

@app.post("/admin/cleanup-sessions")
async def cleanup_sessions():
    """管理端点：清理过期会话"""
    try:
        initial_count = len(whatsapp_router.user_sessions)
        whatsapp_router.cleanup_expired_sessions()
        final_count = len(whatsapp_router.user_sessions)
        
        cleaned_count = initial_count - final_count
        
        return {
            "status": "success",
            "sessions_cleaned": cleaned_count,
            "remaining_sessions": final_count
        }
        
    except Exception as e:
        logger.error(f"Session cleanup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/rebuild-index")
async def rebuild_vector_index():
    """管理端点：重建向量搜索索引"""
    try:
        if not settings.openai_api_key:
            raise HTTPException(status_code=400, detail="OpenAI API key not configured")
        
        await vector_search_client.build_embeddings_index()
        
        return {"status": "success", "message": "Vector index rebuilt successfully"}
        
    except Exception as e:
        logger.error(f"Index rebuild error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/stats")
async def get_stats():
    """管理端点：获取统计信息"""
    try:
        stats = {
            "active_sessions": len(whatsapp_router.user_sessions),
            "provider": settings.channel_provider,
            "loyverse_token_info": loyverse_auth.get_token_info()
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        content={"error": "Internal server error"}
    )

# 导入time模块（修复前面缺少的导入）
import time
from typing import Dict, Any

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.environment == "development"
    )
