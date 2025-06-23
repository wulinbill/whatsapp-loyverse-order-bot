#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deepgram语音转文字工具模块 (Nova-3 优化版)
处理音频转录和相关功能
"""

import os
import time
import logging
from typing import Optional, Dict, Any
import httpx
from deepgram import DeepgramClient, PrerecordedOptions, FileSource

logger = logging.getLogger(__name__)

# 全局Deepgram客户端
deepgram_client = None

def get_deepgram_client() -> DeepgramClient:
    """获取Deepgram客户端实例（懒加载）"""
    global deepgram_client
    if deepgram_client is None:
        api_key = os.getenv("DEEPGRAM_API_KEY")
        if not api_key:
            raise ValueError("DEEPGRAM_API_KEY environment variable is required")
        deepgram_client = DeepgramClient(api_key)
    return deepgram_client

def transcribe_audio(url: str, max_retries: int = 3) -> str:
    """
    转录音频文件为文本，包含重试机制和详细错误处理
    
    Args:
        url: Twilio媒体文件URL
        max_retries: 最大重试次数
        
    Returns:
        转录文本，失败时返回空字符串
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🎤 Transcribing audio with Nova-3 (attempt {attempt + 1}/{max_retries}): {url[:50]}...")
            
            # 验证环境变量
            auth_sid = os.getenv("TWILIO_ACCOUNT_SID")
            auth_token = os.getenv("TWILIO_AUTH_TOKEN")
            dg_key = os.getenv("DEEPGRAM_API_KEY")
            
            if not all([auth_sid, auth_token, dg_key]):
                missing = [k for k, v in {
                    "TWILIO_ACCOUNT_SID": auth_sid,
                    "TWILIO_AUTH_TOKEN": auth_token,
                    "DEEPGRAM_API_KEY": dg_key
                }.items() if not v]
                raise ValueError(f"Missing environment variables: {', '.join(missing)}")
            
            # 下载音频文件
            audio_bytes = download_audio_file(url, auth_sid, auth_token)
            
            if not audio_bytes:
                raise ValueError("Downloaded audio file is empty")
            
            logger.info(f"📁 Downloaded audio file: {len(audio_bytes)} bytes")
            
            # 执行转录 - 使用Nova-3模型
            transcript = perform_transcription_nova3(audio_bytes)
            
            if transcript:
                logger.info(f"✅ Nova-3 transcription successful: '{transcript[:50]}{'...' if len(transcript) > 50 else ''}'")
                return transcript.strip()
            else:
                raise ValueError("Transcription returned empty result")
                
        except Exception as e:
            last_error = e
            logger.warning(f"⚠️ Transcription attempt {attempt + 1} failed: {e}")
            
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 1  # 指数退避
                logger.info(f"⏳ Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"❌ All {max_retries} transcription attempts failed. Last error: {e}")
    
    # 所有重试都失败了
    return ""

def download_audio_file(url: str, auth_sid: str, auth_token: str) -> bytes:
    """
    从Twilio下载音频文件
    
    Args:
        url: 音频文件URL
        auth_sid: Twilio账户SID
        auth_token: Twilio认证令牌
        
    Returns:
        音频文件字节数据
    """
    try:
        auth = (auth_sid, auth_token)
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, auth=auth)
            response.raise_for_status()
            
            audio_bytes = response.content
            
            if len(audio_bytes) == 0:
                raise ValueError("Downloaded audio file is empty")
            
            return audio_bytes
            
    except httpx.TimeoutException:
        raise Exception("Timeout downloading audio from Twilio")
    except httpx.HTTPStatusError as e:
        raise Exception(f"HTTP error downloading audio: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        raise Exception(f"Failed to download audio: {str(e)}")

def perform_transcription_nova3(audio_bytes: bytes) -> str:
    """
    使用Nova-3模型执行音频转录
    
    Args:
        audio_bytes: 音频文件字节数据
        
    Returns:
        转录文本
    """
    try:
        # 获取Deepgram客户端
        client = get_deepgram_client()
        
        # 创建文件源
        payload = FileSource(audio_bytes)
        
        # Nova-3 优化配置
        options = PrerecordedOptions(
            model="nova-3",  # 使用Nova-3模型
            punctuate=True,
            smart_format=True,
            language="multi",  # 支持多语言自动检测
            detect_language=True,
            filler_words=False,  # 过滤填充词
            profanity_filter=False,  # 不过滤敏感词（餐厅环境通常不需要）
            diarize=False,  # 不需要说话人识别
            utterances=False,  # 不需要话语分割
            alternatives=1,  # 只返回最佳结果
            tier="enhanced",  # 使用增强层获得更好质量
            
            # Nova-3 特有的高级功能
            numerals=True,  # 改进数字识别
            measurements=True,  # 改进度量单位识别
            search=True,  # 优化搜索相关内容
            
            # 针对餐厅订餐优化的设置
            keywords=["pollo", "arroz", "papa", "tostones", "combo", "combinacion", "salsa"],  # 餐厅关键词
            
            # Nova-3 支持的语言特定优化
            language_detection=True,
            multichannel=False,
            
            # 提高准确性的设置
            endpointing=300,  # 语音结束检测时间（毫秒）
            vad_turnoff=500,  # 语音活动检测关闭时间
        )
        
        logger.info("🚀 Using Nova-3 model for enhanced transcription accuracy")
        
        # 执行转录
        response = client.listen.prerecorded.v("1").transcribe_file(payload, options)
        
        # 提取转录结果
        transcript = extract_transcript_from_response(response)
        
        return transcript
        
    except Exception as e:
        raise Exception(f"Nova-3 transcription failed: {str(e)}")

def extract_transcript_from_response(response) -> str:
    """
    从Deepgram响应中提取转录文本
    
    Args:
        response: Deepgram API响应
        
    Returns:
        转录文本
    """
    try:
        # 获取转录结果
        results = response.get("results")
        if not results:
            raise ValueError("No results in Deepgram response")
        
        channels = results.get("channels", [])
        if not channels:
            raise ValueError("No channels in results")
        
        alternatives = channels[0].get("alternatives", [])
        if not alternatives:
            raise ValueError("No alternatives in channel")
        
        transcript = alternatives[0].get("transcript", "")
        confidence = alternatives[0].get("confidence", 0.0)
        
        # 记录置信度
        logger.info(f"📊 Nova-3 transcription confidence: {confidence:.2f}")
        
        if confidence < 0.3:
            logger.warning(f"⚠️ Low transcription confidence: {confidence:.2f}")
        elif confidence > 0.8:
            logger.info(f"🎯 High confidence transcription with Nova-3")
        
        # 检测语言
        detected_language = results.get("detected_language")
        if detected_language:
            logger.info(f"🌍 Nova-3 detected language: {detected_language}")
        
        # Nova-3 特有的元数据
        metadata = results.get("metadata", {})
        if metadata:
            model_info = metadata.get("model_info", {})
            if model_info:
                logger.debug(f"🤖 Nova-3 model info: {model_info}")
        
        return transcript
        
    except KeyError as e:
        raise ValueError(f"Unexpected Deepgram response format: missing {e}")
    except Exception as e:
        raise ValueError(f"Failed to extract transcript: {str(e)}")

def get_transcription_status() -> Dict[str, Any]:
    """
    获取Deepgram服务状态（用于健康检查）
    
    Returns:
        服务状态字典
    """
    try:
        # 检查API密钥是否配置
        api_key = os.getenv("DEEPGRAM_API_KEY")
        if not api_key:
            return {
                "status": "unhealthy",
                "service": "deepgram",
                "error": "API key not configured"
            }
        
        # 尝试创建客户端
        client = get_deepgram_client()
        
        # 测试一个小的音频文件（静音）
        test_audio = create_test_audio()
        
        if test_audio:
            payload = FileSource(test_audio)
            options = PrerecordedOptions(
                model="nova-3",  # 使用Nova-3进行测试
                language="en"
            )
            
            # 执行测试转录
            response = client.listen.prerecorded.v("1").transcribe_file(payload, options)
            
            return {
                "status": "healthy",
                "service": "deepgram",
                "model": "nova-3",
                "features": [
                    "multi-language", 
                    "punctuation", 
                    "smart_format",
                    "enhanced_accuracy",
                    "improved_numbers",
                    "better_keywords"
                ]
            }
        else:
            return {
                "status": "healthy",
                "service": "deepgram",
                "model": "nova-3",
                "note": "Client created successfully, skipped test transcription"
            }
            
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "deepgram",
            "model": "nova-3",
            "error": str(e)
        }

def create_test_audio() -> Optional[bytes]:
    """
    创建用于测试的最小音频文件
    
    Returns:
        测试音频字节数据，如果创建失败返回None
    """
    try:
        # 创建一个最小的WAV文件头（44字节）+ 很短的静音数据
        # 这是一个16-bit, 8kHz, mono的WAV文件
        wav_header = bytearray([
            # RIFF header
            0x52, 0x49, 0x46, 0x46,  # "RIFF"
            0x24, 0x00, 0x00, 0x00,  # File size - 8
            0x57, 0x41, 0x56, 0x45,  # "WAVE"
            
            # fmt chunk
            0x66, 0x6D, 0x74, 0x20,  # "fmt "
            0x10, 0x00, 0x00, 0x00,  # Chunk size (16)
            0x01, 0x00,              # Audio format (PCM)
            0x01, 0x00,              # Number of channels (1)
            0x40, 0x1F, 0x00, 0x00,  # Sample rate (8000)
            0x80, 0x3E, 0x00, 0x00,  # Byte rate
            0x02, 0x00,              # Block align
            0x10, 0x00,              # Bits per sample (16)
            
            # data chunk
            0x64, 0x61, 0x74, 0x61,  # "data"
            0x00, 0x00, 0x00, 0x00,  # Data size (0 - silence)
        ])
        
        return bytes(wav_header)
        
    except Exception as e:
        logger.warning(f"Failed to create test audio: {e}")
        return None

def validate_audio_format(content_type: str) -> bool:
    """
    验证音频格式是否支持
    
    Args:
        content_type: 媒体类型
        
    Returns:
        是否支持该格式
    """
    supported_formats = [
        "audio/ogg",
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/x-wav",
        "audio/webm",
        "audio/mp4",
        "audio/aac",
        "audio/flac",  # Nova-3 支持更多格式
        "audio/m4a"
    ]
    
    return content_type in supported_formats

def get_supported_languages() -> list:
    """
    获取Nova-3支持的语言列表
    
    Returns:
        支持的语言代码列表
    """
    return [
        "en",     # English
        "es",     # Spanish  
        "zh",     # Chinese
        "zh-CN",  # Chinese (Simplified)
        "zh-TW",  # Chinese (Traditional)
        "multi",  # Multi-language detection
        "fr",     # French
        "de",     # German
        "it",     # Italian
        "pt",     # Portuguese
        "ja",     # Japanese
        "ko",     # Korean
        "ar",     # Arabic
        "hi",     # Hindi
        "ru",     # Russian
    ]

def get_nova3_capabilities() -> Dict[str, Any]:
    """
    获取Nova-3模型的特有能力
    
    Returns:
        Nova-3能力字典
    """
    return {
        "model": "nova-3",
        "enhanced_accuracy": True,
        "improved_multilingual": True,
        "better_number_recognition": True,
        "advanced_punctuation": True,
        "keyword_detection": True,
        "reduced_hallucination": True,
        "faster_processing": True,
        "supported_languages": len(get_supported_languages()),
        "audio_formats": len([fmt for fmt in [
            "ogg", "mp3", "wav", "webm", "mp4", "aac", "flac", "m4a"
        ]]),
        "optimizations": [
            "restaurant_vocabulary",
            "food_terms",
            "numbers_and_quantities",
            "multilingual_detection"
        ]
    }

def configure_for_restaurant_context() -> PrerecordedOptions:
    """
    为餐厅环境配置Nova-3的专门选项
    
    Returns:
        餐厅优化的PrerecordedOptions
    """
    restaurant_keywords = [
        # 西班牙语餐厅词汇
        "pollo", "carne", "arroz", "papa", "tostones", "combo", "combinacion",
        "salsa", "teriyaki", "agridulce", "plancha", "frito", "brocoli",
        "camarones", "sopa", "huevo", "grande", "pequeño", "mediano",
        
        # 英语餐厅词汇
        "chicken", "beef", "rice", "potato", "combination", "sauce", 
        "fried", "grilled", "shrimp", "soup", "egg", "large", "small", "medium",
        
        # 中文餐厅词汇
        "鸡肉", "牛肉", "米饭", "土豆", "套餐", "酱料", "炸", "烤", "虾", "汤",
        
        # 数量词
        "uno", "dos", "tres", "cuatro", "cinco", "one", "two", "three", "four", "five"
    ]
    
    return PrerecordedOptions(
        model="nova-3",
        punctuate=True,
        smart_format=True,
        language="multi",
        detect_language=True,
        filler_words=False,
        profanity_filter=False,
        diarize=False,
        utterances=False,
        alternatives=1,
        tier="enhanced",
        numerals=True,
        measurements=True,
        search=True,
        keywords=restaurant_keywords,
        language_detection=True,
        endpointing=300,
        vad_turnoff=500,
    )
