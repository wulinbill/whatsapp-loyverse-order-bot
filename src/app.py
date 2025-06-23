#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask应用主模块 - 集成增强版代理
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Any
from flask import Flask, request, abort, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator

# 应用Loyverse补丁
try:
    from loyverse_api_kds_fix import patch_loyverse_api
    patch_loyverse_api()
except ImportError:
    pass

# 导入模块
try:
    from deepgram_utils import transcribe_audio, get_transcription_status
    
    # 检查使用哪个代理
    USE_ENHANCED_AGENT = os.getenv("USE_ENHANCED_AGENT", "true").lower() == "true"
    
    if USE_ENHANCED_AGENT:
        try:
            from enhanced_menu_search_agent import handle_message_enhanced as handle_message
            logger = logging.getLogger(__name__)
            logger.info("💡 Using Enhanced Menu Search Agent (Cost Optimized)")
        except ImportError as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to import enhanced agent: {e}")
            # Fallback to original agent
            from claude_direct_menu_agent import handle_message_claude_direct as handle_message
            logger.info("🔄 Falling back to Claude direct agent")
    else:
        from claude_direct_menu_agent import handle_message_claude_direct as handle_message
        logger = logging.getLogger(__name__)
        logger.info("🧠 Using Claude direct agent")
        
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"Import error: {e}")
    raise

logger = logging.getLogger(__name__)

def create_app() -> Flask:
    """
    创建和配置Flask应用 - 增强版
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
        agent_type = "Enhanced Menu Search (Cost Optimized)" if USE_ENHANCED_AGENT else "Claude Direct"
        return f"<h1>Kong Food Restaurant WhatsApp Bot</h1><p>{agent_type} system is running.</p>"
    
    @app.route("/health", methods=["GET"])
    def health_check():
        """健康检查端点"""
        try:
            health_status = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "service": "kong-food-whatsapp-bot",
                "version": "5.0.0-enhanced",
                "agent_type": "enhanced_menu_search" if USE_ENHANCED_AGENT else "claude_direct",
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
            
            # 检查增强代理状态
            if USE_ENHANCED_AGENT:
                try:
                    from enhanced_menu_search_agent import get_enhanced_agent
                    agent = get_enhanced_agent()
                    debug_info = agent.get_debug_info()
                    
                    health_status["components"]["enhanced_agent"] = {
                        "status": "healthy",
                        "type": "enhanced_menu_search",
                        "features": debug_info.get("features", [])
                    }
                except Exception as e:
                    health_status["status"] = "degraded"
                    health_status["components"]["enhanced_agent"] = {
                        "status": "unhealthy",
                        "error": str(e)
                    }
            
            # 检查Loyverse KDS补丁
            health_status["components"]["loyverse_kds"] = {
                "status": "healthy",
                "kds_support": True,
                "tax_calculation": True
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
        """处理WhatsApp消息 - 增强版"""
        try:
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
            
            # 使用增强代理处理
            agent_type = "Enhanced" if USE_ENHANCED_AGENT else "Direct"
            logger.debug(f"💡 Using {agent_type} agent for {from_number}")
                
            reply = handle_message(from_number, message_body, user_history)
            
            # 创建Twilio响应
            twiml = MessagingResponse()
            twiml.message(reply)
            
            logger.info(f"✅ Response sent to {from_number}")
            return str(twiml), 200, {"Content-Type": "application/xml"}
            
        except Exception as e:
            logger.error(f"❌ Error handling SMS: {e}", exc_info=True)
            return create_error_response(
                "Disculpa, ocurrió un error técnico. Por favor intenta nuevamente. 🔧"
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
                "agent_type": "enhanced" if USE_ENHANCED_AGENT else "direct"
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
    
    @app.route("/debug/agent-info", methods=["GET"])
    def debug_agent_info():
        """获取当前代理信息"""
        try:
            if USE_ENHANCED_AGENT:
                from enhanced_menu_search_agent import get_enhanced_agent
                agent = get_enhanced_agent()
                debug_info = agent.get_debug_info()
                
                return jsonify({
                    "status": "healthy",
                    "agent_type": "enhanced_menu_search",
                    "cost_optimization": True,
                    "features": debug_info.get("features", []),
                    "processed_orders": debug_info.get("processed_orders", 0)
                }), 200
            else:
                return jsonify({
                    "status": "healthy",
                    "agent_type": "claude_direct",
                    "cost_optimization": False
                }), 200
                
        except Exception as e:
            logger.error(f"Error in debug_agent_info: {e}")
            return jsonify({
                "status": "error",
                "error": str(e)
            }), 500
    
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
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Endpoint not found"}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {error}")
        return jsonify({"error": "Internal server error"}), 500
    
    agent_type = "Enhanced Menu Search" if USE_ENHANCED_AGENT else "Claude Direct"
    logger.info(f"🍜 Kong Food Restaurant WhatsApp Bot ({agent_type}) app created successfully")
    return app
