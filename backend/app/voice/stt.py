import os
import io
import logging
from typing import Optional
from fastapi import HTTPException, status
import requests

from app.core.config import settings
from app.models.factory import ModelFactory

logger = logging.getLogger("finpilot.voice.stt")


async def transcribe_audio_groq(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """
    Transcribe speech to text using Groq's whisper-large-v3-turbo model.
    Treats audio input as untrusted data.
    """
    if not audio_bytes or len(audio_bytes) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio payload is empty or corrupted."
        )

    api_key = ModelFactory.get_groq_api_key()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Groq API key is not configured for Whisper speech-to-text. Please set GROQ_API_KEY in .env."
        )

    model_name = settings.GROQ_STT_MODEL or "whisper-large-v3-turbo"

    try:
        # Check if groq package is available
        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            audio_file = (filename, io.BytesIO(audio_bytes))
            transcription = client.audio.transcriptions.create(
                model=model_name,
                file=audio_file,
                response_format="text"
            )
            text_result = str(transcription).strip()
            if not text_result:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No speech could be recognized from the provided audio."
                )
            return text_result

        except ImportError:
            # Fallback to direct Groq HTTP endpoint
            url = "https://api.groq.com/openai/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {api_key}"}
            files = {
                "file": (filename, io.BytesIO(audio_bytes), "audio/wav"),
            }
            data = {
                "model": model_name,
                "response_format": "json"
            }

            resp = requests.post(url, headers=headers, files=files, data=data, timeout=30)
            if resp.status_code != 200:
                logger.error(f"Groq Whisper HTTP error {resp.status_code}: {resp.text}")
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Whisper transcription failed: {resp.text}"
                )

            res_json = resp.json()
            text_result = res_json.get("text", "").strip()
            if not text_result:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No speech detected in audio."
                )
            return text_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Whisper STT transcription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speech recognition error: {str(e)}"
        )
