# 在现有的 app.py 文件中，只需要修改导入和调用部分

# 修改导入部分 (在文件顶部)
try:
    from deepgram_utils import transcribe_audio, get_transcription_status
    # 替换原有的agent导入
    from claude_powered_agent import handle_message_claude_powered
    from claude_client import ClaudeClient
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"Import error: {e}")
    import sys
    logger.error(f"Current directory: {os.getcwd()}")
    logger.error(f"Python path: {sys.path}")
    logger.error(f"Files in current dir: {os.listdir('.')}")
    raise

# 在 handle_sms() 函数中，修改消息处理部分
@app.route("/sms", methods=["POST"])
def handle_sms():
    """
    处理来自Twilio的WhatsApp消息 - Claude驱动版本
    """
    try:
        # ... (现有的验证和音频处理代码保持不变)
        
        # 获取请求参数
        from_number = request.form.get("From")
        message_body = request.form.get("Body", "").strip()
        num_media = int(request.form.get("NumMedia", "0"))
        
        if not from_number:
            logger.error("Missing From parameter in request")
            abort(400, "Missing required parameters")
        
        logger.info(f"📨 Incoming message from {from_number}")
        
        # 处理音频消息 (保持现有逻辑)
        if num_media > 0 and not message_body:
            message_body = handle_audio_message(request)
            
            if not message_body:
                return create_error_response(
                    "Lo siento, no pude entender el audio. ¿Podrías escribir tu mensaje? 🎤❌"
                )
        
        # 验证消息内容 (保持现有逻辑)
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
        
        # ⭐ 这里是关键变化：使用Claude驱动的处理
        reply = handle_message_claude_powered(from_number, message_body, user_history)
        
        # 创建Twilio响应
        twiml = MessagingResponse()
        twiml.message(reply)
        
        logger.info(f"✅ Claude-powered response sent to {from_number}")
        return str(twiml), 200, {"Content-Type": "application/xml"}
        
    except Exception as e:
        logger.error(f"❌ Error handling SMS: {e}", exc_info=True)
        return create_error_response(
            "Disculpa, ocurrió un error técnico. Nuestro equipo ha sido notificado. 🔧"
        )

# 添加新的调试端点
@app.route("/debug/claude-agent", methods=["GET"])
def debug_claude_agent():
    """
    调试Claude代理状态
    """
    try:
        from claude_powered_agent import get_claude_agent
        agent = get_claude_agent()
        debug_info = agent.get_debug_info()
        
        return jsonify({
            "status": "healthy",
            "agent_type": "claude_powered",
            "debug_info": debug_info,
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route("/debug/test-menu-search/<query>", methods=["GET"])
def debug_menu_search(query: str):
    """
    测试Claude的菜单搜索能力
    """
    try:
        from claude_powered_agent import get_claude_agent
        
        # 创建模拟对话来测试菜单识别
        test_history = [
            {"role": "user", "content": query}
        ]
        
        agent = get_claude_agent()
        response = agent.handle_message("debug_user", query, test_history)
        
        return jsonify({
            "query": query,
            "claude_response": response,
            "history": test_history,
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
