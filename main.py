"""更新后的 FastAPI 主应用程序"""
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config import settings, validate_required_settings, print_config_summary
from utils.logger import get_logger, setup_logging
from utils.session_store import get_session_stats, cleanup_expired_sessions
from whatsapp_handler import handle_whatsapp_message, handle_whatsapp_status
from gpt_tools import async_tool_get_menu, refresh_menu_cache, get_tools_stats

# 设置日志级别
setup_logging(settings.log_level)
logger = get_logger(__name__)


# 应用启动和关闭时的生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器"""
    logger.info("WhatsApp 订餐机器人启动中...")
    
    try:
        # 验证配置
        missing_vars = validate_required_settings()
        if missing_vars:
            error_msg = f"缺少必需的环境变量: {', '.join(missing_vars)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        # 打印配置摘要
        if settings.debug_mode:
            print_config_summary()
        
        # 预热菜单缓存
        logger.info("预热菜单缓存...")
        try:
            cache_result = await refresh_menu_cache()
            if cache_result:
                logger.info("菜单缓存预热成功")
            else:
                logger.warning("菜单缓存预热失败，但应用将继续运行")
        except Exception as e:
            logger.warning("菜单缓存预热出错: %s", str(e))
        
        # 验证 Loyverse 连接
        try:
            from loyverse_api import get_store_info
            store_info = await get_store_info()
            if store_info:
                store_name = store_info.get("name", "未知")
                logger.info("Loyverse 连接验证成功，商店: %s", store_name)
            else:
                logger.warning("Loyverse 连接验证失败，但应用将继续运行")
        except Exception as e:
            logger.warning("Loyverse 连接验证出错: %s", str(e))
        
        # 启动后台清理任务
        if not settings.debug_mode:
            cleanup_task = asyncio.create_task(_background_cleanup())
            logger.info("后台清理任务已启动")
        
        logger.info("WhatsApp 订餐机器人启动完成")
        
        yield
        
    except Exception as e:
        logger.error("应用启动失败: %s", str(e))
        raise
    finally:
        # 关闭时执行
        logger.info("WhatsApp 订餐机器人关闭中...")
        
        # 清理资源
        try:
            cleanup_expired_sessions()
            logger.info("已清理会话资源")
        except Exception as e:
            logger.warning("清理会话资源失败: %s", str(e))
        
        logger.info("WhatsApp 订餐机器人已关闭")


async def _background_cleanup():
    """后台清理任务"""
    while True:
        try:
            await asyncio.sleep(300)  # 每5分钟清理一次
            cleanup_count = cleanup_expired_sessions()
            if cleanup_count > 0:
                logger.debug("后台清理了 %d 个过期会话", cleanup_count)
        except asyncio.CancelledError:
            logger.info("后台清理任务被取消")
            break
        except Exception as e:
            logger.error("后台清理任务出错: %s", str(e))
            # 继续运行，不要因为清理错误而停止


# 创建 FastAPI 应用实例
app = FastAPI(
    title="WhatsApp Loyverse 订餐机器人",
    description="集成 Loyverse POS 的 WhatsApp AI 订餐机器人",
    version="2.0.0",
    lifespan=lifespan,
    debug=settings.debug_mode
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug_mode else ["https://api.twilio.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 路由定义
# ---------------------------------------------------------------------------

@app.get("/", response_class=PlainTextResponse)
async def root() -> str:
    """根路径，返回简单的欢迎信息"""
    return "WhatsApp Loyverse 订餐机器人 v2.0 - 运行中"


@app.get("/health", response_class=PlainTextResponse)
async def health_check() -> str:
    """健康检查端点，用于容器编排和监控"""
    return "OK"


@app.get("/health/detailed")
async def detailed_health_check() -> Dict[str, Any]:
    """详细健康检查，返回系统状态信息"""
    try:
        # 检查配置
        missing_vars = validate_required_settings()
        config_status = "healthy" if not missing_vars else "missing_vars"
        
        # 检查 Loyverse 连接
        loyverse_status = "unknown"
        store_info = None
        try:
            from loyverse_api import get_store_info
            store_info = await get_store_info()
            loyverse_status = "connected" if store_info else "disconnected"
        except Exception as e:
            loyverse_status = f"error: {str(e)}"
        
        # 获取会话统计
        session_stats = get_session_stats()
        
        # 获取工具统计
        tools_stats = get_tools_stats()
        
        return {
            "status": "healthy" if config_status == "healthy" and loyverse_status == "connected" else "degraded",
            "timestamp": _get_current_timestamp(),
            "config_status": config_status,
            "missing_config": missing_vars,
            "loyverse_connection": loyverse_status,
            "store_info": {
                "name": store_info.get("name") if store_info else None,
                "id": store_info.get("id") if store_info else None
            } if store_info else None,
            "session_stats": session_stats,
            "tools_stats": tools_stats,
            "settings": {
                "debug_mode": settings.debug_mode,
                "log_level": settings.log_level,
                "openai_model": settings.openai_model,
                "cache_ttl": settings.menu_cache_ttl,
                "session_ttl": settings.session_ttl
            }
        }
        
    except Exception as e:
        logger.error("详细健康检查失败: %s", str(e))
        return {
            "status": "unhealthy",
            "timestamp": _get_current_timestamp(),
            "error": str(e)
        }


@app.post("/whatsapp-webhook")
async def whatsapp_webhook(request: Request):
    """WhatsApp 消息 webhook 端点"""
    try:
        logger.debug("收到 WhatsApp webhook 请求")
        return await handle_whatsapp_message(request)
    except Exception as e:
        logger.error("WhatsApp webhook 处理失败: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/whatsapp-status")
async def whatsapp_status_webhook(request: Request):
    """WhatsApp 消息状态 webhook 端点"""
    try:
        logger.debug("收到 WhatsApp 状态更新请求")
        return await handle_whatsapp_status(request)
    except Exception as e:
        logger.error("WhatsApp 状态 webhook 处理失败: %s", str(e))
        return PlainTextResponse("OK")


@app.get("/menu")
async def get_menu_endpoint():
    """获取当前菜单的 API 端点"""
    try:
        result = await async_tool_get_menu()
        
        if result.get("success"):
            return {
                "success": True,
                "total_items": result["total_items"],
                "menu_items": result["menu_items"]
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"获取菜单失败: {result.get('error', 'Unknown error')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取菜单API失败: %s", str(e))
        raise HTTPException(status_code=500, detail=f"获取菜单失败: {str(e)}")


@app.post("/menu/refresh")
async def refresh_menu_endpoint(background_tasks: BackgroundTasks):
    """手动刷新菜单缓存的 API 端点"""
    try:
        # 在后台执行刷新，避免阻塞请求
        background_tasks.add_task(_refresh_menu_background)
        
        return {
            "success": True,
            "message": "菜单刷新已启动，将在后台执行"
        }
        
    except Exception as e:
        logger.error("启动菜单刷新失败: %s", str(e))
        raise HTTPException(status_code=500, detail=f"启动菜单刷新失败: {str(e)}")


async def _refresh_menu_background():
    """后台刷新菜单缓存"""
    try:
        success = await refresh_menu_cache()
        if success:
            logger.info("后台菜单刷新成功")
        else:
            logger.error("后台菜单刷新失败")
    except Exception as e:
        logger.error("后台菜单刷新异常: %s", str(e))


@app.get("/stats")
async def get_system_stats():
    """获取系统统计信息的 API 端点"""
    try:
        session_stats = get_session_stats()
        tools_stats = get_tools_stats()
        
        return {
            "success": True,
            "timestamp": _get_current_timestamp(),
            "session_stats": session_stats,
            "tools_stats": tools_stats,
            "system_info": {
                "debug_mode": settings.debug_mode,
                "log_level": settings.log_level,
                "cache_ttl": settings.menu_cache_ttl,
                "session_ttl": settings.session_ttl,
                "cleanup_interval": settings.cleanup_interval
            }
        }
        
    except Exception as e:
        logger.error("获取系统统计失败: %s", str(e))
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@app.post("/admin/cleanup")
async def admin_cleanup():
    """管理员清理端点"""
    try:
        # 清理过期会话
        session_cleanup_count = cleanup_expired_sessions()
        
        # 清理工具缓存
        from gpt_tools import clear_tool_cache
        clear_tool_cache()
        
        # 清理解析器缓存
        from gpt_parser import clear_menu_cache
        clear_menu_cache()
        
        return {
            "success": True,
            "message": "清理完成",
            "cleaned_sessions": session_cleanup_count,
            "timestamp": _get_current_timestamp()
        }
        
    except Exception as e:
        logger.error("管理员清理失败: %s", str(e))
        raise HTTPException(status_code=500, detail=f"清理失败: {str(e)}")


@app.post("/admin/reset-stats")
async def admin_reset_stats():
    """重置统计信息"""
    try:
        from gpt_tools import reset_tools_stats
        reset_tools_stats()
        
        return {
            "success": True,
            "message": "统计信息已重置",
            "timestamp": _get_current_timestamp()
        }
        
    except Exception as e:
        logger.error("重置统计失败: %s", str(e))
        raise HTTPException(status_code=500, detail=f"重置统计失败: {str(e)}")


@app.get("/admin/session/{user_id}")
async def get_user_session(user_id: str):
    """获取特定用户的会话信息"""
    try:
        from whatsapp_handler import get_session_info
        session_info = get_session_info(user_id)
        
        return {
            "success": True,
            "session_info": session_info,
            "timestamp": _get_current_timestamp()
        }
        
    except Exception as e:
        logger.error("获取用户会话失败: %s", str(e))
        raise HTTPException(status_code=500, detail=f"获取会话信息失败: {str(e)}")


@app.delete("/admin/session/{user_id}")
async def reset_user_session(user_id: str):
    """重置特定用户的会话"""
    try:
        from whatsapp_handler import reset_user_session
        success = reset_user_session(user_id)
        
        return {
            "success": success,
            "message": "会话已重置" if success else "会话不存在或重置失败",
            "timestamp": _get_current_timestamp()
        }
        
    except Exception as e:
        logger.error("重置用户会话失败: %s", str(e))
        raise HTTPException(status_code=500, detail=f"重置会话失败: {str(e)}")


# ---------------------------------------------------------------------------
# 错误处理
# ---------------------------------------------------------------------------

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """404 错误处理器"""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found", 
            "message": "请求的端点不存在",
            "path": str(request.url.path)
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """500 错误处理器"""
    logger.error("内部服务器错误 (路径: %s): %s", request.url.path, str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error", 
            "message": "服务器内部错误",
            "timestamp": _get_current_timestamp()
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 异常处理器"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP Error",
            "message": exc.detail,
            "status_code": exc.status_code,
            "timestamp": _get_current_timestamp()
        }
    )


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _get_current_timestamp() -> float:
    """获取当前时间戳"""
    import time
    return time.time()


def get_app_info() -> Dict[str, Any]:
    """获取应用信息"""
    return {
        "name": "WhatsApp Loyverse 订餐机器人",
        "version": "2.0.0",
        "description": "集成 Loyverse POS 的 WhatsApp AI 订餐机器人",
        "debug_mode": settings.debug_mode,
        "environment": "development" if settings.debug_mode else "production"
    }


# ---------------------------------------------------------------------------
# 中间件
# ---------------------------------------------------------------------------

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """请求日志中间件"""
    import time
    
    start_time = time.time()
    
    # 记录请求开始
    if settings.debug_mode:
        logger.debug("请求开始: %s %s", request.method, request.url.path)
    
    # 处理请求
    response = await call_next(request)
    
    # 记录请求完成
    process_time = time.time() - start_time
    
    if settings.debug_mode:
        logger.debug("请求完成: %s %s (耗时: %.3fs, 状态码: %d)", 
                    request.method, request.url.path, process_time, response.status_code)
    
    # 添加响应头
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Version"] = "2.0.0"
    
    return response


# ---------------------------------------------------------------------------
# 开发环境启动
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    
    # 开发环境配置
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_reload,
        log_level=settings.log_level.lower(),
        access_log=settings.debug_mode
    )
