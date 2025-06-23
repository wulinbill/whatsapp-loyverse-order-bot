#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude AI客户端模块 (Claude 4 优化版)
处理与Anthropic Claude API的所有交互
"""

import os
import logging
import time
from typing import List, Dict, Optional, Any
from anthropic import Anthropic, APIError, RateLimitError, APITimeoutError

logger = logging.getLogger(__name__)

class ClaudeClient:
    """Claude AI客户端，处理对话和API调用"""
    
    def __init__(self):
        """初始化Claude客户端"""
        # 获取API密钥
        self.api_key = os.getenv("CLAUDE_API_KEY")
        if not self.api_key:
            raise ValueError("CLAUDE_API_KEY environment variable is required")
        
        # 初始化客户端
        self.client = Anthropic(api_key=self.api_key)
        
        # 配置模型 - 默认使用 Claude 4 Sonnet
        self.model = os.getenv("CLAUDE_MODEL", "claude-4-sonnet-20250514")
        
        # Claude 4 优化的API调用配置
        self.default_max_tokens = 2000  # Claude 4 可以处理更多tokens
        self.timeout = 45  # 稍微增加超时时间
        self.max_retries = 3
        
        # Claude 4 性能提示
        if "claude-4" in self.model.lower():
            logger.info(f"🚀 Claude 4 client initialized: {self.model}")
            logger.info("⚡ Enhanced performance and reasoning capabilities enabled")
        else:
            logger.info(f"🤖 Claude client initialized with model: {self.model}")
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        与Claude进行对话
        
        Args:
            messages: 消息列表，格式为 [{"role": "user/assistant/system", "content": "..."}]
            **kwargs: 额外参数 (max_tokens, temperature等)
            
        Returns:
            Claude的回复内容
        """
        try:
            # Claude 4 优化的参数处理
            max_tokens = kwargs.get('max_tokens', self.default_max_tokens)
            temperature = kwargs.get('temperature', 0.7)
            
            # Claude 4 支持更精细的温度控制
            if "claude-4" in self.model.lower():
                temperature = min(max(temperature, 0.0), 1.0)  # 确保范围正确
            
            # 分离系统消息和对话历史
            system_message = ""
            conversation = []
            
            for msg in messages:
                if msg["role"] == "system":
                    system_message = msg["content"]
                elif msg["role"] in ["user", "assistant"]:
                    conversation.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
            
            # 确保对话以用户消息开始
            if not conversation or conversation[0]["role"] != "user":
                raise ValueError("Conversation must start with a user message")
            
            logger.debug(f"Sending {len(conversation)} messages to {self.model}")
            
            # 调用Claude API (使用重试机制)
            response = self._make_api_call_with_retry(
                system=system_message if system_message else None,
                messages=conversation,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            # 提取回复内容
            if response.content and len(response.content) > 0:
                reply = response.content[0].text
                logger.info(f"✅ {self.model} responded: {reply[:100]}{'...' if len(reply) > 100 else ''}")
                return reply
            else:
                logger.error("Empty response from Claude API")
                return self._get_fallback_response()
                
        except Exception as e:
            logger.error(f"❌ Claude API error: {e}")
            return self._handle_api_error(e)
    
    def _make_api_call_with_retry(self, **api_params) -> Any:
        """
        带重试机制的API调用
        
        Args:
            **api_params: API参数
            
        Returns:
            API响应
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    **api_params
                )
                return response
                
            except RateLimitError as e:
                last_error = e
                # Claude 4 可能有不同的速率限制
                wait_time = (2 ** attempt) * 2  # 稍微增加等待时间
                logger.warning(f"Rate limit hit, retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})")
                time.sleep(wait_time)
                
            except APITimeoutError as e:
                last_error = e
                logger.warning(f"API timeout, retrying (attempt {attempt + 1}/{self.max_retries})")
                time.sleep(2)
                
            except APIError as e:
                # 对于4xx错误，不重试
                if hasattr(e, 'status_code') and 400 <= e.status_code < 500:
                    raise e
                    
                last_error = e
                logger.warning(f"API error, retrying (attempt {attempt + 1}/{self.max_retries}): {e}")
                time.sleep(1)
                
        # 所有重试都失败
        raise last_error
    
    def _handle_api_error(self, error: Exception) -> str:
        """
        处理API错误并返回适当的回复
        
        Args:
            error: 错误对象
            
        Returns:
            错误回复消息
        """
        if isinstance(error, RateLimitError):
            return "Lo siento, estoy experimentando mucho tráfico ahora. Por favor intenta de nuevo en unos momentos."
        
        elif isinstance(error, APITimeoutError):
            return "La conexión está tardando más de lo normal. ¿Podrías repetir tu mensaje?"
        
        elif isinstance(error, APIError):
            return "Estoy teniendo problemas técnicos temporales. ¿Podrías intentar nuevamente?"
        
        else:
            return "Disculpa, ocurrió un error inesperado. Por favor intenta de nuevo."
    
    def _get_fallback_response(self) -> str:
        """获取后备响应"""
        return "¡Hola! Soy el asistente de Kong Food Restaurant. ¿En qué puedo ayudarte con tu pedido hoy?"
    
    def validate_configuration(self) -> Dict[str, Any]:
        """
        验证Claude客户端配置
        
        Returns:
            配置状态字典
        """
        try:
            # 测试API连接
            test_response = self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            
            # Claude 4 特殊标识
            model_info = {
                "model": self.model,
                "is_claude_4": "claude-4" in self.model.lower(),
                "max_tokens": self.default_max_tokens,
                "timeout": self.timeout
            }
            
            return {
                "status": "healthy",
                "api_accessible": True,
                "message": f"Claude client is working properly with {self.model}",
                **model_info
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "model": self.model,
                "api_accessible": False,
                "error": str(e),
                "message": "Claude client has configuration issues"
            }
    
    def get_usage_info(self) -> Dict[str, Any]:
        """
        获取使用信息（如果API支持）
        
        Returns:
            使用信息字典
        """
        return {
            "model": self.model,
            "is_claude_4": "claude-4" in self.model.lower(),
            "max_tokens": self.default_max_tokens,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "capabilities": self._get_model_capabilities()
        }
    
    def _get_model_capabilities(self) -> Dict[str, Any]:
        """
        获取模型能力信息
        
        Returns:
            模型能力字典
        """
        if "claude-4" in self.model.lower():
            return {
                "enhanced_reasoning": True,
                "improved_accuracy": True,
                "better_multilingual": True,
                "larger_context": True,
                "faster_responses": True
            }
        else:
            return {
                "standard_capabilities": True
            }
