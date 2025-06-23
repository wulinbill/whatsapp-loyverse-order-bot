#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kong Food Restaurant WhatsApp订餐机器人 - 修复版本
使用Claude AI进行智能对话处理
"""

import os
import sys
import logging
import pathlib

# 确保正确的Python路径设置
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')

# 添加src目录到Python路径的最前面
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# 同时设置环境变量
os.environ['PYTHONPATH'] = src_dir + ':' + os.environ.get('PYTHONPATH', '')

# 修复模块导入问题
def setup_module_paths():
    """设置模块搜索路径"""
    try:
        # 确保所有必要的路径都在sys.path中
        paths_to_add = [
            current_dir,
            src_dir,
            os.path.join(src_dir, 'src'),  # 处理嵌套的src目录
        ]
        
        for path in paths_to_add:
            if os.path.exists(path) and path not in sys.path:
                sys.path.insert(0, path)
                
        logging.info(f"📁 Module paths configured: {len(sys.path)} paths")
        logging.debug(f"Python path: {sys.path[:5]}...")  # 只显示前5个路径
        
    except Exception as e:
        logging.error(f"Error setting up module paths: {e}")

# 设置路径
setup_module_paths()

# 配置日志记录 - 提前配置避免导入错误
def setup_logging():
    """配置日志系统"""
    try:
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        
        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        
        # 设置外部库的日志级别
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("twilio").setLevel(logging.WARNING)
        logging.getLogger("anthropic").setLevel(logging.WARNING)
        
        logger = logging.getLogger(__name__)
        logger.info("🍜 Kong Food Restaurant Bot logging initialized")
        return logger
        
    except Exception as e:
        print(f"Failed to setup logging: {e}")
        return logging.getLogger(__name__)

logger = setup_logging()

# 尝试导入应用模块
def import_app_safely():
    """安全导入应用模块"""
    try:
        # 打印调试信息
        logger.info(f"🔍 Current working directory: {os.getcwd()}")
        logger.info(f"📁 Source directory: {src_dir}")
        logger.info(f"📂 Directory contents: {os.listdir('.')}")
        
        if os.path.exists('src'):
            logger.info(f"📂 Source directory contents: {os.listdir('src')}")
        
        # 尝试导入app模块
        from app import create_app
        logger.info("✅ Successfully imported create_app")
        return create_app
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        logger.info("🔄 Attempting alternative import methods...")
        
        # 尝试直接从src目录导入
        try:
            sys.path.insert(0, os.path.join(current_dir, 'src'))
            from app import create_app
            logger.info("✅ Successfully imported create_app (alternative method)")
            return create_app
        except ImportError as e2:
            logger.error(f"❌ Alternative import failed: {e2}")
            
        # 最后的后备方案：创建最小应用
        logger.warning("⚠️ Using minimal fallback application")
        return create_minimal_app
        
    except Exception as e:
        logger.error(f"❌ Unexpected error during import: {e}")
        return create_minimal_app

def create_minimal_app():
    """创建最小化的Flask应用作为后备方案"""
    try:
        from flask import Flask, jsonify, request
        
        app = Flask(__name__)
        
        @app.route('/')
        def index():
            return "<h1>Kong Food Restaurant WhatsApp Bot</h1><p>Minimal fallback mode active</p>"
        
        @app.route('/health')
        def health():
            return jsonify({
                "status": "degraded",
                "mode": "minimal_fallback",
                "message": "Running in minimal mode due to import issues"
            })
        
        @app.route('/sms', methods=['POST'])
        def handle_sms():
            return jsonify({"error": "Service temporarily unavailable"}), 503
        
        logger.warning("⚠️ Minimal fallback app created")
        return app
        
    except Exception as e:
        logger.error(f"❌ Failed to create minimal app: {e}")
        raise

# 导入应用创建函数
create_app_func = import_app_safely()

# 创建Flask应用实例
try:
    app = create_app_func()
    logger.info("✅ Flask application created successfully")
except Exception as e:
    logger.error(f"❌ Failed to create Flask application: {e}")
    app = create_minimal_app()

if __name__ == '__main__':
    try:
        # 从环境变量获取端口，默认为 10000 (Render配置)
        port = int(os.environ.get("PORT", 10000))
        
        logger.info(f"🚀 Starting Kong Food Restaurant Bot on port {port}")
        
        # 检查是否在Render环境中
        if os.getenv("RENDER"):
            logger.info("🌐 Running in Render environment")
            # Render环境中直接运行
            app.run(host="0.0.0.0", port=port, debug=False)
        else:
            # 本地开发环境
            logger.info("💻 Running in local environment")
            
            # 尝试使用waitress (如果可用)
            try:
                from waitress import serve
                logger.info("🍽️ Using Waitress server")
                serve(app, host="0.0.0.0", port=port)
            except ImportError:
                logger.info("🔧 Using Flask development server")
                app.run(host="0.0.0.0", port=port, debug=True)
                
    except Exception as e:
        logger.error(f"❌ Failed to start server: {e}")
        # 最后的尝试：使用基础Flask服务器
        try:
            app.run(host="0.0.0.0", port=8080, debug=False)
        except:
            logger.critical("💀 All server startup attempts failed")
            sys.exit(1)
