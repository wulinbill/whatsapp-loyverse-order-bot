#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask应用主模块 - Claude 4直接菜单匹配版本
处理WhatsApp消息和HTTP请求路由
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Any
from flask import Flask, request, abort, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator

# 导入模块 - 优先使用Claude直接菜单匹配
try:
    from deepgram_utils import transcribe_audio, get_transcription_status
    
    # 检查是否启用Claude直接菜单匹配
    USE_CLAUDE_DIRECT = os.getenv("USE_CLAUDE_DIRECT", "true").lower() == "true"
    
    if USE_CLAUDE_DIRECT:
        try:
            from claude_direct_menu_agent import handle_message_claude_direct as handle_message
            logger = logging.getLogger(__name__)
            logger.info("🧠 Using Claude 4 Direct Menu Matching Agent")
        except ImportError as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to import Claude direct agent: {e}")
            logger.info("🔄 Falling back to Claude powered agent")
            try:
                from claude_powered_agent import handle_message_claude_powered as handle_message
                logger.info("🧠 Using Claude-powered agent")
            except ImportError:
                from agent import handle_message
                logger.info("🔧 Using original agent")
    else:
        logger = logging.getLogger(__name__)
        logger.info("🔧 Claude direct matching disabled by config")
        try:
            from claude_powered_agent import handle_message_claude_powered as handle_message
            logger.info("🧠 Using Claude-powered agent")
        except ImportError:
            from agent import handle_message
            logger.info("🔧 Using original agent")
        
    from claude_client import ClaudeClient
    
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"Import error: {e}")
    import sys
    logger.error(f"Current directory: {os.getcwd()}")
    logger.error(f"Python path: {sys.path}")
    logger.error(f"Files in current dir: {os.listdir('.')}")
    raise

logger = logging.getLogger(__name__)

def create_app() -> Flask:
    """
    创建和配置Flask应用 - Claude 4直接菜单匹配版本
    
    Returns:
        配置好的Flask应用实例
    """
    app = Flask(__name__)
    
    # 应用配置
    app.config['JSON_AS_ASCII'] = False
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
    
    # 存储用户会话
    sessions: Dict[str, List[Dict[str, str]]] = {}
    
    # Twilio请求验证器
    twilio_validator = None
    if os.getenv('TWILIO_AUTH_TOKEN'):
        twilio_validator = RequestValidator(os.getenv('TWILIO_AUTH_TOKEN'))
    
    @app.before_request
    def log_request_info():
        """记录请求信息"""
        if request.endpoint not in ['health_check', 'index']:
            logger.debug(f"📥 {request.method} {request.path} from {request.remote_addr}")
    
    @app.route("/", methods=["GET"])
    def index():
        """根端点"""
        agent_type = "Claude 4 Direct Menu Matching" if USE_CLAUDE_DIRECT else "Claude Powered"
        return f"<h1>Kong Food Restaurant WhatsApp Bot</h1><p>{agent_type} system is running.</p>"
    
    @app.route("/health", methods=["GET"])
    def health_check():
        """
        健康检查端点 - 包含Claude直接菜单匹配状态
        """
        try:
            health_status = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "service": "kong-food-whatsapp-bot",
                "version": "4.0.0-claude-direct-menu",
                "agent_type": "claude_direct" if USE_CLAUDE_DIRECT else "claude_powered",
                "components": {}
            }
            
            # 检查环境变量
            required_env_vars = [
                "CLAUDE_API_KEY",
                "TWILIO_ACCOUNT_SID", 
                "TWILIO_AUTH_TOKEN",
                "LOYVERSE_CLIENT_ID",
                "LOYVERSE_CLIENT_SECRET"
            ]
            
            missing_vars = [var for var in required_env_vars if not os.getenv(var)]
            
            if missing_vars:
                health_status["status"] = "unhealthy"
                health_status["components"]["environment"] = {
                    "status": "unhealthy",
                    "missing_variables": missing_vars
                }
            else:
                health_status["components"]["environment"] = {"status": "healthy"}
            
            # 检查Claude直接菜单代理状态
            if USE_CLAUDE_DIRECT:
                try:
                    from claude_direct_menu_agent import get_claude_direct_agent
                    agent = get_claude_direct_agent()
                    debug_info = agent.get_debug_info()
                    
                    health_status["components"]["claude_direct_agent"] = {
                        "status": "healthy",
                        "type": "claude_direct_menu_matching",
                        "system_prompt_loaded": debug_info.get("system_prompt_length", 0) > 2000,
                        "model": debug_info.get("claude_model", "unknown"),
                        "menu_integration": debug_info.get("menu_integration", "unknown")
                    }
                    
                except Exception as e:
                    health_status["status"] = "degraded"
                    health_status["components"]["claude_direct_agent"] = {
                        "status": "unhealthy",
                        "error": str(e)
                    }
            else:
                # 检查Claude powered agent
                try:
                    from claude_powered_agent import get_claude_agent
                    agent = get_claude_agent()
                    debug_info = agent.get_debug_info()
                    
                    health_status["components"]["claude_agent"] = {
                        "status": "healthy",
                        "type": "claude_powered",
                        "system_prompt_loaded": debug_info.get("system_prompt_length", 0) > 1000,
                        "model": debug_info.get("claude_model", "unknown")
                    }
                    
                except Exception as e:
                    health_status["status"] = "degraded"
                    health_status["components"]["claude_agent"] = {
                        "status": "unhealthy",
                        "error": str(e)
                    }
            
            # 检查菜单数据
            try:
                from tools import validate_menu_data
                menu_status = validate_menu_data()
                
                health_status["components"]["menu_data"] = {
                    "status": menu_status.get("status", "unknown"),
                    "total_items": menu_status.get("total_items", 0),
                    "categories": menu_status.get("total_categories", 0)
                }
                
            except Exception as e:
                health_status["components"]["menu_data"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
            
            # 检查Deepgram状态
            try:
                deepgram_status = get_transcription_status()
                health_status["components"]["deepgram"] = deepgram_status
            except Exception as e:
                health_status["components"]["deepgram"] = {
                    "status": "unknown",
                    "error": str(e)
                }
            
            # 添加会话统计
            health_status["components"]["sessions"] = {
                "status": "healthy",
                "active_sessions": len(sessions),
                "total_messages": sum(len(hist) for hist in sessions.values())
            }
            
            # 返回适当的HTTP状态码
            status_code = 200 if health_status["status"] == "healthy" else 503
            
            return jsonify(health_status), status_code
            
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return jsonify({
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }), 500
    
    @app.route("/sms", methods=["POST"])
    def handle_sms():
        """
        处理来自Twilio的WhatsApp消息 - Claude 4直接菜单匹配版本
        """
        try:
            # 验证Twilio请求
            if twilio_validator and os.getenv('VALIDATE_TWILIO_REQUESTS', 'false').lower() == 'true':
                signature = request.headers.get('X-Twilio-Signature', '')
                if not twilio_validator.validate(request.url, request.form, signature):
                    logger.warning(f"Invalid Twilio signature from {request.remote_addr}")
                    abort(403, "Invalid signature")
            
            # 获取请求参数
            from_number = request.form.get("From")
            message_body = request.form.get("Body", "").strip()
            num_media = int(request.form.get("NumMedia", "0"))
            
            if not from_number:
                logger.error("Missing From parameter in request")
                abort(400, "Missing required parameters")
            
            logger.info(f"📨 Message from {from_number}: '{message_body[:50]}{'...' if len(message_body) > 50 else ''}'")
            
            # 处理音频消息
            if num_media > 0 and not message_body:
                message_body = handle_audio_message(request)
                
                if not message_body:
                    return create_error_response(
                        "Lo siento, no pude entender el audio. ¿Podrías escribir tu mensaje? 🎤❌"
                    )
            
            # 验证消息内容
            if not validate_message_content(message_body):
                logger.warning(f"Invalid message content from {from_number}")
                return create_error_response(
                    "Por favor envía un mensaje válido. 📝"
                )
            
            # 获取或创建用户会话
            user_history = sessions.setdefault(from_number, [])
            
            # 清理历史记录
            user_history = cleanup_history(user_history, max_length=20)
            sessions[from_number] = user_history
            
            # 🧠 使用Claude 4直接菜单匹配处理
            agent_type = "Claude 4 Direct Menu" if USE_CLAUDE_DIRECT else "Claude Powered"
            logger.debug(f"🧠 Using {agent_type} processing for {from_number}")
                
            reply = handle_message(from_number, message_body, user_history)
            
            # 创建Twilio响应
            twiml = MessagingResponse()
            twiml.message(reply)
            
            logger.info(f"✅ Response sent to {from_number}")
            return str(twiml), 200, {"Content-Type": "application/xml"}
            
        except Exception as e:
            logger.error(f"❌ Error handling SMS: {e}", exc_info=True)
            return create_error_response(
                "Disculpa, ocurrió un error técnico. Nuestro equipo ha sido notificado. 🔧"
            )
    
    @app.route("/whatsapp-webhook", methods=["POST"])
    def handle_whatsapp_webhook():
        """处理WhatsApp webhook的备用端点"""
        logger.info("Received request on /whatsapp-webhook, forwarding to /sms handler.")
        return handle_sms()
    
    def handle_audio_message(request) -> str:
        """处理音频消息"""
        try:
            media_content_type = request.form.get("MediaContentType0", "")
            
            if not media_content_type.startswith("audio"):
                logger.warning(f"Unsupported media type: {media_content_type}")
                return ""
            
            media_url = request.form.get("MediaUrl0")
            if not media_url:
                logger.warning("No media URL provided")
                return ""
            
            logger.info(f"🎤 Transcribing audio: {media_content_type}")
            transcription = transcribe_audio(media_url)
            
            if transcription:
                logger.info(f"✅ Audio transcribed: {transcription[:50]}...")
            else:
                logger.warning("Audio transcription failed")
            
            return transcription
            
        except Exception as e:
            logger.error(f"Error handling audio: {e}", exc_info=True)
            return ""
    
    def create_error_response(message: str) -> tuple:
        """创建错误响应"""
        twiml = MessagingResponse()
        twiml.message(message)
        return str(twiml), 200, {"Content-Type": "application/xml"}
    
    @app.route("/sessions", methods=["GET"])
    def get_sessions():
        """获取活跃会话信息"""
        try:
            session_info = {}
            for phone, history in sessions.items():
                session_info[phone] = {
                    "user_id": phone,
                    "total_messages": len(history),
                    "user_messages": sum(1 for msg in history if msg.get("role") == "user"),
                    "assistant_messages": sum(1 for msg in history if msg.get("role") == "assistant"),
                    "last_activity": "now"
                }
            
            return jsonify({
                "total_sessions": len(sessions),
                "sessions": session_info,
                "agent_type": "claude_direct" if USE_CLAUDE_DIRECT else "claude_powered"
            }), 200
            
        except Exception as e:
            logger.error(f"Error getting sessions: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/sessions/<phone_number>", methods=["DELETE"])
    def clear_session(phone_number: str):
        """清除指定用户的会话"""
        try:
            if phone_number in sessions:
                del sessions[phone_number]
                logger.info(f"🗑️ Session cleared for {phone_number}")
                return jsonify({"message": f"Session cleared for {phone_number}"}), 200
            else:
                return jsonify({"message": f"No session found for {phone_number}"}), 404
                
        except Exception as e:
            logger.error(f"Error clearing session: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/debug/claude-direct", methods=["GET"])
    def debug_claude_direct():
        """调试Claude直接菜单匹配代理状态"""
        try:
            if USE_CLAUDE_DIRECT:
                from claude_direct_menu_agent import get_claude_direct_agent
                agent = get_claude_direct_agent()
                debug_info = agent.get_debug_info()
                
                return jsonify({
                    "status": "healthy",
                    "agent_type": "claude_direct_menu_matching",
                    "debug_info": debug_info,
                    "use_claude_direct": USE_CLAUDE_DIRECT,
                    "timestamp": datetime.now().isoformat()
                }), 200
            else:
                return jsonify({
                    "status": "info",
                    "agent_type": "not_using_claude_direct",
                    "use_claude_direct": USE_CLAUDE_DIRECT,
                    "message": "Claude direct menu matching is disabled"
                }), 200
                
        except Exception as e:
            logger.error(f"Error in debug_claude_direct: {e}")
            return jsonify({
                "status": "error",
                "error": str(e)
            }), 500

    @app.route("/debug/test-menu-search/<query>", methods=["GET"])
    def debug_menu_search(query: str):
        """测试菜单搜索能力"""
        try:
            if USE_CLAUDE_DIRECT:
                from claude_direct_menu_agent import get_claude_direct_agent
                
                # 创建模拟对话来测试菜单识别
                test_history = []
                
                agent = get_claude_direct_agent()
                response = agent.handle_message("debug_user", query, test_history)
                
                return jsonify({
                    "query": query,
                    "agent_type": "claude_direct_menu_matching",
                    "claude_response": response,
                    "history": test_history,
                    "timestamp": datetime.now().isoformat()
                }), 200
            else:
                # 测试原始或Claude powered代理
                test_history = []
                response = handle_message("debug_user", query, test_history)
                
                return jsonify({
                    "query": query,
                    "agent_type": "fallback_agent",
                    "response": response,
                    "history": test_history,
                    "timestamp": datetime.now().isoformat()
                }), 200
                
        except Exception as e:
            logger.error(f"Error in debug_menu_search: {e}")
            return jsonify({
                "query": query,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }), 500

    @app.route("/debug/switch-agent", methods=["POST"])
    def switch_agent():
        """切换代理类型（仅用于测试）"""
        try:
            new_agent = request.json.get("agent_type", "claude_direct") if request.is_json else "claude_direct"
            
            # 注意：这个切换只在当前会话有效
            global USE_CLAUDE_DIRECT
            USE_CLAUDE_DIRECT = new_agent.lower() == "claude_direct"
            
            return jsonify({
                "message": f"Switched to {'Claude Direct Menu' if USE_CLAUDE_DIRECT else 'fallback'} agent",
                "current_agent": "claude_direct" if USE_CLAUDE_DIRECT else "fallback",
                "note": "This change is temporary and will reset on server restart"
            }), 200
            
        except Exception as e:
            logger.error(f"Error switching agent: {e}")
            return jsonify({"error": str(e)}), 500
    
    def cleanup_history(history: List[Dict[str, str]], max_length: int = 20) -> List[Dict[str, str]]:
        """清理对话历史"""
        if len(history) <= max_length:
            return history
        return history[-max_length:]

    def validate_message_content(content: str) -> bool:
        """验证消息内容"""
        if not content or not content.strip():
            return False
        if len(content) > 2000:
            return False
        return True
    
    # 错误处理器
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({"error": "Bad request", "message": str(error)}), 400
    
    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({"error": "Forbidden", "message": str(error)}), 403
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Endpoint not found"}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {error}")
        return jsonify({"error": "Internal server error"}), 500
    
    # 请求日志
    @app.after_request
    def log_response(response):
        if request.endpoint not in ['health_check']:
            logger.debug(f"📤 {response.status_code} {request.method} {request.path}")
        return response
    
    agent_type = "Claude 4 Direct Menu Matching" if USE_CLAUDE_DIRECT else "Fallback Agent"
    logger.info(f"🍜 Kong Food Restaurant WhatsApp Bot ({agent_type}) app created successfully")
    return app
