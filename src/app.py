#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask应用主模块
处理WhatsApp消息和HTTP请求路由
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Any
from flask import Flask, request, abort, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator

from deepgram_utils import transcribe_audio, get_transcription_status
from agent import handle_message, cleanup_history, validate_message_content, get_session_info
from claude_client import ClaudeClient

logger = logging.getLogger(__name__)

def create_app() -> Flask:
    """
    创建和配置Flask应用
    
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
        if request.endpoint not in ['health_check']:  # 排除健康检查的日志
            logger.debug(f"📥 {request.method} {request.path} from {request.remote_addr}")
    
    @app.route("/health", methods=["GET"])
    def health_check():
        """
        健康检查端点
        检查各个组件的状态
        """
        try:
            health_status = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "service": "kong-food-whatsapp-bot",
                "version": "2.0.0",
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
            
            # 检查Claude客户端
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
        处理来自Twilio的WhatsApp消息
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
            
            # 处理消息并获取回复
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
                session_info[phone] = get_session_info(phone, history)
            
            return jsonify({
                "total_sessions": len(sessions),
                "sessions": session_info
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
    
    logger.info("🍜 Kong Food Restaurant WhatsApp Bot app created successfully")
    return app