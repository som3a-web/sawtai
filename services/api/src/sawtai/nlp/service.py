"""Public NLP-orchestration facade."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    confidence: float
    duration_seconds: float | None = None


@dataclass(frozen=True)
class SynthesizedSpeech:
    path: Path
    mime_type: str
    duration_seconds: float | None = None


class SpeechToTextProvider(Protocol):
    name: str
    version: str

    async def transcribe(self, *, audio: bytes, mime_type: str) -> Transcript: ...


class TextToSpeechProvider(Protocol):
    name: str
    version: str

    async def synthesize(self, *, text: str, language: str) -> SynthesizedSpeech: ...


class SpeechProviderUnavailable(RuntimeError):
    """Raised until a sovereign STT or TTS provider is configured."""
