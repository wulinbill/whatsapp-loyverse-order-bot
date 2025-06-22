import os, httpx, logging
from deepgram import Deepgram
import time
from typing import Optional

logger = logging.getLogger(__name__)
DG_CLIENT = Deepgram(os.getenv("DEEPGRAM_API_KEY"))

def transcribe_audio(url: str, max_retries: int = 3) -> str:
    """
    转录音频文件为文本，包含重试机制和详细错误处理
    
    Args:
        url: Twilio 媒体文件 URL
        max_retries: 最大重试次数
        
    Returns:
        转录文本，失败时返回空字符串
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
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
            
            logger.info(f"Transcribing audio from {url[:50]}... (attempt {attempt + 1}/{max_retries})")
            
            # 下载音频文件
            auth = (auth_sid, auth_token)
            try:
                response = httpx.get(url, auth=auth, timeout=30)
                response.raise_for_status()
                audio_bytes = response.content
                
                if len(audio_bytes) == 0:
                    raise ValueError("Downloaded audio file is empty")
                    
                logger.info(f"Downloaded audio file: {len(audio_bytes)} bytes")
                
            except httpx.TimeoutException:
                raise Exception("Timeout downloading audio from Twilio")
            except httpx.HTTPStatusError as e:
                raise Exception(f"HTTP error downloading audio: {e.response.status_code}")
            
            # Deepgram 转录
            try:
                res = DG_CLIENT.transcription.prerecorded(
                    {"buffer": audio_bytes, "mimetype": "audio/ogg"},
                    {
                        "model": "nova", 
                        "punctuate": True, 
                        "smart_format": True,
                        "language": "es",  # 支持西班牙语
                        "detect_language": True  # 自动语言检测
                    }
                )
                
                # 提取转录结果
                transcript = res["results"]["channels"][0]["alternatives"][0]["transcript"]
                confidence = res["results"]["channels"][0]["alternatives"][0]["confidence"]
                
                logger.info(f"Transcription successful: '{transcript}' (confidence: {confidence:.2f})")
                
                if confidence < 0.3:
                    logger.warning(f"Low transcription confidence: {confidence:.2f}")
                
                return transcript.strip()
                
            except KeyError as e:
                raise Exception(f"Unexpected Deepgram response format: missing {e}")
            except Exception as e:
                raise Exception(f"Deepgram transcription failed: {str(e)}")
                
        except Exception as e:
            last_error = e
            logger.warning(f"Transcription attempt {attempt + 1} failed: {e}")
            
            if attempt < max_retries - 1:
                # 指数退避
                wait_time = (2 ** attempt) * 1
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"All {max_retries} transcription attempts failed. Last error: {e}")
    
    # 所有重试都失败了
    return ""

def get_transcription_status() -> dict:
    """
    获取 Deepgram 服务状态（用于健康检查）
    """
    try:
        # 简单的 API 调用测试
        test_response = DG_CLIENT.transcription.prerecorded(
            {"buffer": b"", "mimetype": "audio/wav"},
            {"model": "nova"}
        )
        return {"status": "healthy", "service": "deepgram"}
    except Exception as e:
        return {"status": "unhealthy", "service": "deepgram", "error": str(e)}
