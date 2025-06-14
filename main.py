"""FastAPI 主应用程序"""
import os
from contextlib import asynccontextmanager
from typing import Dict, Any
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from utils.logger import get_logger
from whatsapp_handler import handle_whatsapp_message, handle_whatsapp_status
from loyverse_api import get_store_info

# 在应用启动时加载环境变量
load_dotenv()

logger = get_logger(__name__)

# 应用启动和关闭时的生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器"""
    # 启动时执行
    logger.info("WhatsApp 订餐机器人启动中...")
    
    # 验证关键环境变量
    required_vars = [
        "OPENAI_API_KEY",
        "LOYVERSE_CLIENT_ID", 
        "LOYVERSE_CLIENT_SECRET",
        "LOYVERSE_REFRESH_TOKEN",
        "LOYVERSE_STORE_ID"
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error("缺少必需的环境变量: %s", ", ".join(missing_vars))
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    # 验证 Loyverse 连接
    try:
        store_info = await get_store_info()
        if store_info:
            logger.info("Loyverse 连接验证成功，商店: %s", store_info.get("name", "未知"))
        else:
            logger.warning("Loyverse 连接验证失败，但应用将继续运行")
    except Exception as e:
        logger.warning("Loyverse 连接验证出错: %s", e)
    
    logger.info("WhatsApp 订餐机器人启动完成")
    
    yield
    
    # 关闭时执行
    logger.info("WhatsApp 订餐机器人关闭中...")
    # 这里可以添加清理逻辑
    logger.info("WhatsApp 订餐机器人已关闭")


# 创建 FastAPI 应用实例
app = FastAPI(
    title="WhatsApp Loyverse 订餐机器人",
    description="集成 Loyverse POS 的 WhatsApp AI 订餐机器人",
    version="1.0.0",
    lifespan=lifespan
)

# 添加 CORS 中间件（如果需要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
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
    return "WhatsApp Loyverse 订餐机器人 - 运行中"


@app.get("/health", response_class=PlainTextResponse)
async def health_check() -> str:
    """健康检查端点，用于容器编排和监控"""
    return "OK"


@app.get("/health/detailed")
async def detailed_health_check() -> Dict[str, Any]:
    """详细健康检查，返回系统状态信息"""
    try:
        # 检查 Loyverse 连接
        store_info = await get_store_info()
        loyverse_status = "connected" if store_info else "disconnected"
        
        # 检查环境变量
        required_vars = [
            "OPENAI_API_KEY",
            "LOYVERSE_CLIENT_ID", 
            "LOYVERSE_CLIENT_SECRET",
            "LOYVERSE_REFRESH_TOKEN",
            "LOYVERSE_STORE_ID"
        ]
        
        env_status = {var: "configured" if os.getenv(var) else "missing" for var in required_vars}
        
        return {
            "status": "healthy",
            "loyverse_connection": loyverse_status,
            "environment_variables": env_status,
            "store_info": {
                "name": store_info.get("name") if store_info else None,
                "id": store_info.get("id") if store_info else None
            } if store_info else None
        }
        
    except Exception as e:
        logger.error("详细健康检查失败: %s", e)
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@app.post("/whatsapp-webhook")
async def whatsapp_webhook(request: Request):
    """WhatsApp 消息 webhook 端点
    
    接收来自 Twilio 的 WhatsApp 消息并处理
    """
    try:
        logger.debug("收到 WhatsApp webhook 请求")
        return await handle_whatsapp_message(request)
    except Exception as e:
        logger.error("WhatsApp webhook 处理失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/whatsapp-status")
async def whatsapp_status_webhook(request: Request):
    """WhatsApp 消息状态 webhook 端点（可选）
    
    接收来自 Twilio 的消息状态更新
    """
    try:
        logger.debug("收到 WhatsApp 状态更新请求")
        return await handle_whatsapp_status(request)
    except Exception as e:
        logger.error("WhatsApp 状态 webhook 处理失败: %s", e)
        # 状态更新失败不应该影响主要功能
        return PlainTextResponse("OK")


@app.get("/menu")
async def get_menu_endpoint():
    """获取当前菜单的 API 端点（用于调试）"""
    try:
        from loyverse_api import get_menu_items
        from gpt_parser import get_menu_item_names
        
        menu_data = await get_menu_items()
        menu_names = get_menu_item_names(menu_data)
        
        return {
            "success": True,
            "total_items": len(menu_names),
            "menu_items": menu_names
        }
    except Exception as e:
        logger.error("获取菜单失败: %s", e)
        raise HTTPException(status_code=500, detail=f"获取菜单失败: {str(e)}")


# ---------------------------------------------------------------------------
# 错误处理
# ---------------------------------------------------------------------------

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """404 错误处理器"""
    return JSONResponse(
        status_code=404,
        content={"error": "Not Found", "message": "请求的端点不存在"}
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """500 错误处理器"""
    logger.error("内部服务器错误: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "message": "服务器内部错误"}
    )


# ---------------------------------------------------------------------------
# 开发环境启动
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    
    # 开发环境配置
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 开发时启用热重载
        log_level="info"
    )
