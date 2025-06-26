import asyncio
import time
from typing import Optional, Dict, Any
from deepgram import DeepgramClient, PrerecordedOptions
import httpx

from ..config import get_settings
from ..logger import get_logger, business_logger

settings = get_settings()
logger = get_logger(__name__)

class DeepgramSpeechClient:
    """Deepgram语音转文字客户端"""
    
    def __init__(self):
        self.client = DeepgramClient(settings.deepgram_api_key)
        self.model = settings.deepgram_model
    
    async def transcribe_audio_url(self, audio_url: str, user_id: str) -> Optional[str]:
        """
        从音频URL转录文字
        
        Args:
            audio_url: 音频文件URL
            user_id: 用户ID
            
        Returns:
            转录的文字内容，如果失败返回None
        """
        start_time = time.time()
        
        try:
            logger.info(f"Starting audio transcription for user {user_id} from URL: {audio_url}")
            
            # 配置转录选项
            options = PrerecordedOptions(
                model=self.model,
                language="es",  # 主要语言西班牙语
                detect_language=True,  # 自动检测语言
                punctuate=True,
                diarize=False,
                smart_format=True,
                utterances=False,
                alternatives=1
            )
            
            # 执行转录
            response = await asyncio.to_thread(
                self.client.listen.prerecorded.v("1").transcribe_url,
                {"url": audio_url},
                options
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 提取转录文字
            transcript = self._extract_transcript(response)
            
            if transcript:
                business_logger.log_inbound_message(
                    user_id=user_id,
                    message_type="voice",
                    content=transcript,
                    metadata={
                        "audio_size_bytes": len(audio_data),
                        "mime_type": mime_type,
                        "duration_ms": duration_ms,
                        "detected_language": self._get_detected_language(response)
                    }
                )
                logger.info(f"Transcription successful for user {user_id}: {transcript[:100]}...")
            else:
                business_logger.log_error(
                    user_id=user_id,
                    stage="speech",
                    error_code="TRANSCRIPTION_EMPTY",
                    error_msg="No transcript found in response"
                )
                
            return transcript
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="speech",
                error_code="TRANSCRIPTION_FAILED",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Audio transcription failed for user {user_id}: {e}")
            return None
    
    def _extract_transcript(self, response) -> Optional[str]:
        """从Deepgram响应中提取转录文字"""
        try:
            if hasattr(response, 'results') and response.results:
                channels = response.results.channels
                if channels and len(channels) > 0:
                    alternatives = channels[0].alternatives
                    if alternatives and len(alternatives) > 0:
                        transcript = alternatives[0].transcript
                        return transcript.strip() if transcript else None
            return None
        except Exception as e:
            logger.error(f"Error extracting transcript: {e}")
            return None
    
    def _get_detected_language(self, response) -> Optional[str]:
        """获取检测到的语言"""
        try:
            if hasattr(response, 'results') and response.results:
                metadata = getattr(response.results, 'metadata', None)
                if metadata and hasattr(metadata, 'detected_language'):
                    return metadata.detected_language
            return None
        except Exception as e:
            logger.error(f"Error getting detected language: {e}")
            return None

# 全局Deepgram客户端实例
deepgram_client = DeepgramSpeechClient()
            transcript = self._extract_transcript(response)
            
            if transcript:
                business_logger.log_inbound_message(
                    user_id=user_id,
                    message_type="voice",
                    content=transcript,
                    metadata={
                        "audio_url": audio_url,
                        "duration_ms": duration_ms,
                        "detected_language": self._get_detected_language(response)
                    }
                )
                logger.info(f"Transcription successful for user {user_id}: {transcript[:100]}...")
            else:
                business_logger.log_error(
                    user_id=user_id,
                    stage="speech",
                    error_code="TRANSCRIPTION_EMPTY",
                    error_msg="No transcript found in response"
                )
                
            return transcript
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="speech",
                error_code="TRANSCRIPTION_FAILED",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Audio transcription failed for user {user_id}: {e}")
            return None
    
    async def transcribe_audio_bytes(self, audio_data: bytes, user_id: str, mime_type: str = "audio/ogg") -> Optional[str]:
        """
        从音频字节数据转录文字
        
        Args:
            audio_data: 音频字节数据
            user_id: 用户ID
            mime_type: 音频MIME类型
            
        Returns:
            转录的文字内容，如果失败返回None
        """
        start_time = time.time()
        
        try:
            logger.info(f"Starting audio transcription for user {user_id} from bytes data")
            
            # 配置转录选项
            options = PrerecordedOptions(
                model=self.model,
                language="es",  # 主要语言西班牙语
                detect_language=True,  # 自动检测语言
                punctuate=True,
                diarize=False,
                smart_format=True,
                utterances=False,
                alternatives=1
            )
            
            # 执行转录
            response = await asyncio.to_thread(
                self.client.listen.prerecorded.v("1").transcribe_file,
                {"buffer": audio_data, "mimetype": mime_type},
                options
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 提
