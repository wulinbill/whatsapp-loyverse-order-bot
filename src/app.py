#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask应用主模块 - Claude 4驱动版本
处理WhatsApp消息和HTTP请求路由
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Any
from flask import Flask, request, abort, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator

# 使用相对导入，确保模块能正确找到
try:
    from deepgram_utils import transcribe_audio, get_transcription_status
    # 使用Claude驱动的代理，支持环境变量切换
    USE_CLAUDE_AGENT = os.getenv("USE_CLAUDE_AGENT", "true").lower() == "true"
    
    if USE_CLAUDE_AGENT:
        try:
            from claude_powered_agent import handle_message_claude_powered as handle_message
            logger = logging.getLogger(__name__)
            logger.info("🧠 Using Claude-powered agent")
        except ImportError as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to import Claude agent: {e}")
            logger.info("🔄 Falling back to original agent")
            from agent import handle_message
    else:
        from agent import handle_message
        logger = logging.getLogger(__name__)
        logger.info("🔧 Using original code-based agent")
        
    from claude_client import ClaudeClient
    
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"Import error: {e}")
    # 为了调试，让我们看看当前目录的内容
    import sys
    logger.error(f"Current directory: {os.getcwd()}")
    logger.error(f"Python path: {sys.path}")
    logger.error(f"Files in current dir: {os.listdir('.')}")
    raise

logger = logging.getLogger(__name__)

def create_app() -> Flask:
    """
    创建和配置Flask应用 - Claude 4驱动版本
    
    Returns:
        配置好的Flask应用实例
    """
    app = Flask(__name__)
    
    # 应用配置
    app.config['JSON_AS_ASCII'] = False  # 支持中文JSON
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
    
    # 存储用户会话 (生产环境建议使用Redis)
    sessions: Dict[str, List[Dict[str, str]]] = {}
    
    # Twilio请求验证器
    twilio_validator = None
    if os.getenv('TWILIO_AUTH_TOKEN'):
        twilio_validator = RequestValidator(os.getenv('TWILIO_AUTH_TOKEN'))
    
    @app.before_request
    def log_request_info():
        """记录请求信息"""
        if request.endpoint not in ['health_check', 'index']:  # 排除健康检查和根端点的日志
            logger.debug(f"📥 {request.method} {request.path} from {request.remote_addr}")
    
    @app.route("/", methods=["GET"])
    def index():
        """
        根端点，返回欢迎信息
        """
        return "<h1>Welcome to Kong Food Restaurant WhatsApp Bot!</h1><p>Claude 4-powered ordering system is running.</p>"
    
    @app.route("/health", methods=["GET"])
    def health_check():
        """
        健康检查端点 - 包含Claude代理状态
        检查各个组件的状态
        """
        try:
            health_status = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "service": "kong-food-whatsapp-bot",
                "version": "3.0.0-claude-powered",
                "agent_type": "claude_powered" if USE_CLAUDE_AGENT else "original",
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
            
            # 检查Claude代理状态
            if USE_CLAUDE_AGENT:
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
            else:
                # 检查原始Claude客户端
                try:
                    claude_client = ClaudeClient()
                    claude_status = claude_client.validate_configuration()
                    health_status["components"]["claude"] = claude_status
                    
                    if claude_status["status"] != "healthy":
                        health_status["status"] = "degraded"
                        
                except Exception as e:
                    health_status["status"] = "unhealthy"
                    health_status["components"]["claude"] = {
                        "status": "unhealthy",
                        "error": str(e)
                    }
            
            # 检查菜单数据
            try:
                from tools import load_menu_data
                menu_data = load_menu_data()
                
                total_items = 0
                for category in menu_data.get("menu_categories", {}).values():
                    if isinstance(category, dict) and "items" in category:
                        total_items += len(category["items"])
                
                health_status["components"]["menu_data"] = {
                    "status": "healthy",
                    "total_items": total_items,
                    "categories": len(menu_data.get("menu_categories", {}))
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
        处理来自Twilio的WhatsApp消息 - Claude驱动版本
        """
        try:
            # 验证Twilio请求（生产环境推荐）
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
            
            logger.info(f"📨 Incoming message from {from_number}")
            
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
            
            # 🧠 使用Claude驱动的消息处理
            if USE_CLAUDE_AGENT:
                logger.debug(f"🧠 Using Claude-powered processing for {from_number}")
            else:
                logger.debug(f"🔧 Using original processing for {from_number}")
                
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
        """
        处理来自Twilio的WhatsApp消息的备用端点
        """
        logger.info("Received request on /whatsapp-webhook, forwarding to /sms handler.")
        return handle_sms()
    
    def handle_audio_message(request) -> str:
        """
        处理音频消息
        
        Args:
            request: Flask请求对象
            
        Returns:
            转录的文本内容
        """
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
                logger.info(f"✅ Audio transcribed successfully: {transcription[:50]}...")
            else:
                logger.warning("Audio transcription failed or returned empty")
            
            return transcription
            
        except Exception as e:
            logger.error(f"Error handling audio message: {e}", exc_info=True)
            return ""
    
    def create_error_response(message: str) -> tuple:
        """
        创建错误响应
        
        Args:
            message: 错误消息
            
        Returns:
            Twilio响应元组
        """
        twiml = MessagingResponse()
        twiml.message(message)
        return str(twiml), 200, {"Content-Type": "application/xml"}
    
    @app.route("/sessions", methods=["GET"])
    def get_sessions():
        """
        获取活跃会话信息（管理端点）
        """
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
                "agent_type": "claude_powered" if USE_CLAUDE_AGENT else "original"
            }), 200
            
        except Exception as e:
            logger.error(f"Error getting sessions: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/sessions/<phone_number>", methods=["DELETE"])
    def clear_session(phone_number: str):
        """
        清除指定用户的会话
        
        Args:
            phone_number: 用户电话号码
        """
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
    
    @app.route("/sessions/cleanup", methods=["POST"])
    def cleanup_sessions():
        """
        清理所有会话（管理端点）
        """
        try:
            cleared_count = len(sessions)
            sessions.clear()
            logger.info(f"🧹 Cleared {cleared_count} sessions")
            
            return jsonify({
                "message": f"Cleared {cleared_count} sessions",
                "remaining_sessions": len(sessions)
            }), 200
            
        except Exception as e:
            logger.error(f"Error during session cleanup: {e}")
            return jsonify({"error": str(e)}), 500
    
    # Claude代理相关的调试端点
    @app.route("/debug/claude-agent", methods=["GET"])
    def debug_claude_agent():
        """
        调试Claude代理状态
        """
        try:
            if USE_CLAUDE_AGENT:
                from claude_powered_agent import get_claude_agent
                agent = get_claude_agent()
                debug_info = agent.get_debug_info()
                
                return jsonify({
                    "status": "healthy",
                    "agent_type": "claude_powered",
                    "debug_info": debug_info,
                    "use_claude_agent": USE_CLAUDE_AGENT,
                    "timestamp": datetime.now().isoformat()
                }), 200
            else:
                return jsonify({
                    "status": "info",
                    "agent_type": "original",
                    "use_claude_agent": USE_CLAUDE_AGENT,
                    "message": "Using original code-based agent"
                }), 200
                
        except Exception as e:
            logger.error(f"Error in debug_claude_agent: {e}")
            return jsonify({
                "status": "error",
                "error": str(e)
            }), 500

    @app.route("/debug/test-menu-search/<query>", methods=["GET"])
    def debug_menu_search(query: str):
        """
        测试菜单搜索能力
        """
        try:
            if USE_CLAUDE_AGENT:
                from claude_powered_agent import get_claude_agent
                
                # 创建模拟对话来测试菜单识别
                test_history = []
                
                agent = get_claude_agent()
                response = agent.handle_message("debug_user", query, test_history)
                
                return jsonify({
                    "query": query,
                    "agent_type": "claude_powered",
                    "claude_response": response,
                    "history": test_history,
                    "timestamp": datetime.now().isoformat()
                }), 200
            else:
                # 测试原始代理
                test_history = []
                response = handle_message("debug_user", query, test_history)
                
                return jsonify({
                    "query": query,
                    "agent_type": "original",
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

    @app.route("/debug/agent-comparison/<query>", methods=["GET"])
    def compare_agents(query: str):
        """对比两个代理的响应"""
        try:
            results = {"query": query}
            
            # 测试Claude代理
            if USE_CLAUDE_AGENT:
                try:
                    from claude_powered_agent import handle_message_claude_powered
                    test_history_claude = []
                    claude_response = handle_message_claude_powered("test_user", query, test_history_claude.copy())
                    results["claude_agent"] = {
                        "response": claude_response,
                        "available": True
                    }
                except Exception as e:
                    results["claude_agent"] = {
                        "error": str(e),
                        "available": False
                    }
            
            # 测试原始代理
            try:
                from agent import handle_message as handle_original
                test_history_original = []
                original_response = handle_original("test_user", query, test_history_original.copy())
                results["original_agent"] = {
                    "response": original_response,
                    "available": True
                }
            except Exception as e:
                results["original_agent"] = {
                    "error": str(e),
                    "available": False
                }
            
            # 添加对比分析
            if "claude_agent" in results and "original_agent" in results:
                claude_resp = results["claude_agent"].get("response", "")
                original_resp = results["original_agent"].get("response", "")
                
                results["comparison"] = {
                    "length_diff": len(claude_resp) - len(original_resp),
                    "has_json_claude": "##JSON##" in claude_resp,
                    "has_json_original": "##JSON##" in original_resp,
                    "claude_longer": len(claude_resp) > len(original_resp)
                }
            
            return jsonify(results), 200
            
        except Exception as e:
            logger.error(f"Error in compare_agents: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/debug/switch-agent", methods=["POST"])
    def switch_agent():
        """切换代理类型（仅用于测试）"""
        try:
            new_agent = request.json.get("agent_type", "claude") if request.is_json else "claude"
            
            # 注意：这个切换只在当前会话有效，重启后会重置为环境变量值
            global USE_CLAUDE_AGENT
            USE_CLAUDE_AGENT = new_agent.lower() == "claude"
            
            return jsonify({
                "message": f"Switched to {'Claude' if USE_CLAUDE_AGENT else 'original'} agent",
                "current_agent": "claude_powered" if USE_CLAUDE_AGENT else "original",
                "note": "This change is temporary and will reset on server restart"
            }), 200
            
        except Exception as e:
            logger.error(f"Error switching agent: {e}")
            return jsonify({"error": str(e)}), 500
    
    def cleanup_history(history: List[Dict[str, str]], max_length: int = 20) -> List[Dict[str, str]]:
        """
        清理对话历史，保持在合理长度
        
        Args:
            history: 对话历史
            max_length: 最大保留消息数量
            
        Returns:
            清理后的历史
        """
        if len(history) <= max_length:
            return history
        
        # 保留最近的消息
        return history[-max_length:]

    def validate_message_content(content: str) -> bool:
        """
        验证消息内容是否有效
        
        Args:
            content: 消息内容
            
        Returns:
            是否有效
        """
        if not content or not content.strip():
            return False
        
        # 检查长度限制
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
    
    agent_type = "Claude 4-powered" if USE_CLAUDE_AGENT else "Original code-based"
    logger.info(f"🍜 Kong Food Restaurant WhatsApp Bot ({agent_type}) app created successfully")
    return app
