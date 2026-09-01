from __future__ import annotations

import asyncio
import re
import tempfile
from pathlib import Path

from ..config import settings
from ..schemas import VoiceTranscription


class VoiceError(RuntimeError):
    pass


LANGUAGE_RE = re.compile(r"^(?:auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?)$")


def _configured_paths() -> tuple[Path, Path]:
    if not settings.whisper_cpp_binary or not settings.whisper_cpp_model:
        raise VoiceError("Voice transcription is not configured. Set WHISPER_CPP_BINARY and WHISPER_CPP_MODEL.")
    binary = Path(settings.whisper_cpp_binary).expanduser().resolve()
    model = Path(settings.whisper_cpp_model).expanduser().resolve()
    if not binary.is_file():
        raise VoiceError(f"whisper.cpp binary not found: {binary}")
    if not model.is_file():
        raise VoiceError(f"whisper.cpp model not found: {model}")
    return binary, model


def _validate_wav(audio: bytes) -> None:
    if not audio:
        raise VoiceError("Audio payload is empty")
    if len(audio) > settings.voice_max_audio_bytes:
        raise VoiceError(f"Audio payload exceeds {settings.voice_max_audio_bytes} bytes")
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise VoiceError("Voice endpoint accepts PCM WAV audio only")


async def transcribe_wav(audio: bytes, language: str = "auto") -> VoiceTranscription:
    _validate_wav(audio)
    language = language.strip() or "auto"
    if not LANGUAGE_RE.fullmatch(language):
        raise VoiceError("Invalid language code")

    binary, model = _configured_paths()
    with tempfile.TemporaryDirectory(prefix="genesis-voice-") as temp_dir:
        root = Path(temp_dir)
        input_path = root / "input.wav"
        output_prefix = root / "transcript"
        input_path.write_bytes(audio)

        process = await asyncio.create_subprocess_exec(
            str(binary),
            "-m",
            str(model),
            "-f",
            str(input_path),
            "-otxt",
            "-of",
            str(output_prefix),
            "-np",
            "-nt",
            "-l",
            language,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=settings.voice_timeout_seconds)
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise VoiceError("whisper.cpp transcription timed out") from exc

        if process.returncode != 0:
            detail = (stderr or stdout).decode("utf-8", errors="replace").strip()[-2000:]
            raise VoiceError(f"whisper.cpp failed with exit code {process.returncode}: {detail}")

        transcript_path = output_prefix.with_suffix(".txt")
        if transcript_path.is_file():
            text = transcript_path.read_text(encoding="utf-8", errors="replace").strip()
        else:
            text = stdout.decode("utf-8", errors="replace").strip()
        if not text:
            raise VoiceError("whisper.cpp returned an empty transcript")

        return VoiceTranscription(
            text=text,
            engine="whisper.cpp",
            model=model.name,
            language=language,
        )
