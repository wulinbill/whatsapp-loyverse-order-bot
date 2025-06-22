import os, httpx, logging
from deepgram import Deepgram

logger = logging.getLogger(__name__)
DG_CLIENT = Deepgram(os.getenv("DEEPGRAM_API_KEY"))

def transcribe_audio(url: str) -> str:
    try:
        auth = (os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
        audio_bytes = httpx.get(url, auth=auth, timeout=30).content
        res = DG_CLIENT.transcription.prerecorded(
            {"buffer": audio_bytes, "mimetype": "audio/ogg"},
            {"model": "nova", "punctuate": True, "smart_format": True}
        )
        return res["results"]["channels"][0]["alternatives"][0]["transcript"]
    except Exception as e:
        logger.error("Deepgram transcription error: %s", e, exc_info=True)
        return ""
