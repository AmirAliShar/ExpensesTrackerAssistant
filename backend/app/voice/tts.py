import io
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger("finpilot.voice.tts")


async def synthesize_speech(text: str) -> Optional[bytes]:
    """
    Synthesize spoken text into audio bytes using configured TTS provider.
    Supported providers: edge-tts, gTTS, or browser synthesis fallback.
    """
    clean_text = text.strip()
    if not clean_text:
        return None

    provider = settings.TTS_PROVIDER.lower()
    voice_model = settings.TTS_MODEL or "en-US-ChristopherNeural"

    # 1. Edge-TTS (high quality neural voice)
    if provider in ("edge-tts", "edge_tts"):
        try:
            import edge_tts
            communicate = edge_tts.Communicate(clean_text, voice_model)
            out_stream = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    out_stream.write(chunk["data"])
            out_stream.seek(0)
            return out_stream.read()
        except ImportError:
            logger.info("edge-tts package not installed. Trying fallback...")
        except Exception as e:
            logger.warning(f"edge-tts error: {e}. Trying fallback...")

    # 2. gTTS fallback
    try:
        from gtts import gTTS
        tts = gTTS(text=clean_text, lang="en")
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp.read()
    except ImportError:
        logger.debug("gTTS package not installed.")
    except Exception as e:
        logger.warning(f"gTTS error: {e}")

    # If server-side TTS engines are unavailable, return None so the frontend uses its built-in Web Speech API
    return None
