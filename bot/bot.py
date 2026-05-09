"""WhisperSqueak Telegram Bot — transcribes voice messages via NanoScribe's FunASR.

Uses aiogram 3.x for Telegram integration and httpx for async HTTP calls to
NanoScribe's OpenAI-compatible /v1/audio/transcriptions endpoint.

Environment variables (see bot/.env.example):
  TELEGRAM_TOKEN   — Bot token from @BotFather (required)
  ALLOWED_UIDS     — Comma-separated Telegram user IDs (required)
  NANOSCRIBE_URL   — NanoScribe backend URL (default: http://funasr:8000)
  TELEGRAM_API_ID  — For local API server (optional)
  TELEGRAM_API_HASH — For local API server (optional)
  TELEGRAM_API_URL — Local API server URL (default: http://telegram-api:8081)
  TELEGRAM_API_ID  — Required when using local API server
  TELEGRAM_API_HASH — Required when using local API server
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path

import httpx
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

# ── Config ──────────────────────────────────────────────────────────

load_dotenv()

TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
ALLOWED_UIDS: set[int] = set()
NANOSCRIBE_URL: str = os.getenv("NANOSCRIBE_URL", "http://funasr:8000").rstrip("/")
TELEGRAM_API_URL: str | None = os.getenv("TELEGRAM_API_URL")
LOCAL_FILES_DIR = os.getenv("LOCAL_FILES_DIR", "/var/lib/telegram-bot-api")


async def _download_file(bot: Bot, file_obj, destination: Path) -> None:
    """Download a Telegram file. Uses local filesystem when local API is active."""
    if TELEGRAM_API_URL:
        # Local Telegram API mode: files are on the shared filesystem
        tg_file = await bot.get_file(file_obj.file_id)
        local_path = Path(tg_file.file_path)  # type: ignore[arg-type]
        if local_path.exists():
            import shutil
            shutil.copy2(local_path, destination)
            logger.debug("Copied local file: %s", local_path)
            return
        logger.warning("Local file not found at %s, falling back to HTTP", local_path)

    await bot.download(file_obj, destination=destination)

# Parse ALLOWED_UIDS from env
_raw_uids = os.getenv("ALLOWED_UIDS", "")
if _raw_uids:
    for uid_str in _raw_uids.split(","):
        uid_str = uid_str.strip()
        if uid_str:
            try:
                ALLOWED_UIDS.add(int(uid_str))
            except ValueError:
                logging.warning("Invalid UID in ALLOWED_UIDS: %s", uid_str)

# Chunking configuration
CHUNK_DURATION_MS: int = 60_000  # 60 seconds per chunk
CHUNK_OVERLAP_MS: int = 2_000  # 2-second overlap between chunks
LONG_AUDIO_THRESHOLD_MS: int = 60_000  # Switch to chunked mode above 60s

# ── Logging ─────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bot")

# ── Validation ──────────────────────────────────────────────────────


def _validate_config() -> None:
    """Ensure required env vars are set, exit otherwise."""
    missing: list[str] = []
    if not TELEGRAM_TOKEN:
        missing.append("TELEGRAM_TOKEN")
    if not ALLOWED_UIDS:
        missing.append("ALLOWED_UIDS")
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")


# ── Whitelist ───────────────────────────────────────────────────────


def _is_allowed(user_id: int) -> bool:
    """Check if a Telegram user is on the whitelist."""
    return user_id in ALLOWED_UIDS


# ── Audio helpers ───────────────────────────────────────────────────


def _get_audio_duration_ms(file_path: Path) -> int:
    """Return audio duration in milliseconds using pydub."""
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(str(file_path))
        return len(audio)
    except Exception as exc:
        logger.warning("Failed to get audio duration: %s", exc)
        return 0


def _split_audio_chunks(
    file_path: Path,
    chunk_duration_ms: int = CHUNK_DURATION_MS,
    overlap_ms: int = CHUNK_OVERLAP_MS,
) -> list[Path]:
    """Split audio into overlapping chunks using pydub.

    Returns a list of temporary WAV file paths.  The caller is responsible
    for cleaning them up.
    """
    from pydub import AudioSegment

    audio = AudioSegment.from_file(str(file_path))
    # Convert to 16kHz mono 16-bit for consistent normalization
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)

    total_ms = len(audio)
    chunks: list[Path] = []
    pos = 0

    while pos < total_ms:
        end = min(pos + chunk_duration_ms, total_ms)
        chunk = audio[pos:end]

        # Write to temp WAV
        tmp = tempfile.NamedTemporaryFile(
            suffix=".wav",
            prefix=f"chunk_{pos}_",
            delete=False,
        )
        tmp.close()
        chunk_path = Path(tmp.name)
        chunk.export(str(chunk_path), format="wav")
        chunks.append(chunk_path)

        if end >= total_ms:
            break

        # Advance with overlap
        pos = end - overlap_ms
        # Guard against zero/negative advance on very short audio
        if pos <= (end - chunk_duration_ms):
            pos = end

    return chunks


# ── Transcription ───────────────────────────────────────────────────


async def _transcribe_single(
    client: httpx.AsyncClient,
    audio_path: Path,
    hotwords: str | None = None,
) -> dict | None:
    """POST a single audio file to NanoScribe and return the verbose_json result.

    Returns the parsed JSON dict on success, or None on failure.
    """
    try:
        with open(audio_path, "rb") as f:
            data: dict[str, str] = {
                "model": "whisper-1",
                "response_format": "verbose_json",
            }
            if hotwords:
                data["prompt"] = hotwords

            files = {"file": (audio_path.name, f, "audio/wav")}

            t0 = time.monotonic()
            resp = await client.post(
                f"{NANOSCRIBE_URL}/v1/audio/transcriptions",
                data=data,
                files=files,
                timeout=httpx.Timeout(600.0, connect=30.0),
            )
            elapsed = time.monotonic() - t0

            if resp.status_code != 200:
                logger.error(
                    "Transcription failed: HTTP %s — %s",
                    resp.status_code,
                    resp.text[:300],
                )
                return None

            result = resp.json()
            logger.info(
                "Chunk transcribed in %.1fs, %d segments, %d chars",
                elapsed,
                len(result.get("segments", [])),
                len(result.get("text", "")),
            )
            return result

    except httpx.TimeoutException:
        logger.error("Transcription request timed out")
        return None
    except httpx.ConnectError:
        logger.error("Cannot connect to NanoScribe at %s", NANOSCRIBE_URL)
        return None
    except Exception:
        logger.exception("Transcription request failed")
        return None


def _merge_chunk_text(previous_text: str, chunk_text: str) -> str:
    """Merge overlapping chunk text by removing the common prefix overlap.

    Finds the longest suffix of *previous_text* that matches a prefix of
    *chunk_text*, and appends only the non-overlapping portion.
    """
    if not previous_text:
        return chunk_text.strip()

    prev = previous_text.strip()
    curr = chunk_text.strip()

    # Find the longest overlap: try decreasing lengths from max possible
    max_overlap = min(len(prev), len(curr), 200)  # Cap search at 200 chars
    for overlap_len in range(max_overlap, 0, -1):
        if prev[-overlap_len:] == curr[:overlap_len]:
            merged = prev + curr[overlap_len:]
            return merged

    # No overlap found — just concatenate
    return prev + " " + curr


# ── Message formatting ──────────────────────────────────────────────


def _format_transcript(text: str, duration_ms: int | None = None) -> str:
    """Format the transcript for Telegram reply."""
    if not text:
        return "_(no speech detected)_"

    # Escape Telegram Markdown reserved characters in the transcript text
    # so they don't break formatting.
    escaped = _escape_telegram(text)

    if duration_ms is not None:
        duration_s = duration_ms / 1000
        mins = int(duration_s // 60)
        secs = int(duration_s % 60)
        header = f"📝 *Transcript* _{mins}:{secs:02d}_\n\n"
        return header + escaped

    return escaped


def _escape_telegram(text: str) -> str:
    """Escape characters that Telegram interprets as MarkdownV2 special chars."""
    special = r"_*[]()~`>#+-=|{}.!"
    result: list[str] = []
    for ch in text:
        if ch in special:
            result.append("\\" + ch)
        else:
            result.append(ch)
    return "".join(result)


def _format_error(reason: str) -> str:
    """Format an error message for the user."""
    return f"❌ {reason}"


# ── Bot setup ───────────────────────────────────────────────────────

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Send welcome message."""
    await message.answer(
        "Hi! I transcribe voice messages and audio files using FunASR. "
        "Send me a voice note or audio file to get started\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Send usage instructions."""
    await message.answer(
        "📋 *Supported formats*: MP3, WAV, OGG, M4A, FLAC, WebM, Opus, AAC\\.\n\n"
        "Send any voice message or audio file\\. "
        "Long audio is processed in chunks with progressive results\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ── Voice message handler ───────────────────────────────────────────


@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot) -> None:
    """Handle Telegram voice messages."""
    if message.from_user is None:
        return
    if not _is_allowed(message.from_user.id):
        logger.info("Rejected voice from non-whitelisted user %s", message.from_user.id)
        return

    logger.info(
        "Voice message from %s (duration=%ss)",
        message.from_user.id,
        message.voice.duration if message.voice else "?",
    )

    # Download voice as OGG
    voice = message.voice
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        voice_path = Path(tmp.name)

    try:
        await _download_file(bot, voice, voice_path)
        await _process_audio_file(message, bot, voice_path, source_name="voice.ogg")
    finally:
        try:
            voice_path.unlink()
        except OSError:
            pass


# ── Audio file handler ──────────────────────────────────────────────


@router.message(F.audio | F.document)
async def handle_audio(message: Message, bot: Bot) -> None:
    """Handle audio files and documents that might be audio."""
    if message.from_user is None:
        return
    if not _is_allowed(message.from_user.id):
        logger.info("Rejected audio from non-whitelisted user %s", message.from_user.id)
        return

    # Determine the file to download
    file_obj = message.audio or message.document
    if file_obj is None:
        return

    # For documents, check extension
    if message.document:
        filename = message.document.file_name or "audio"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        supported = {"wav", "mp3", "m4a", "aac", "webm", "ogg", "opus", "mp4", "mpeg", "mpga", "flac"}
        if ext not in supported:
            await message.answer(
                _format_error(
                    f"Unsupported format \\.{ext}\\. "
                    f"Supported: {', '.join(sorted(supported))}\\.",
                ),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        suffix = f".{ext}"
    else:
        # Telegram audio object — file extension from mime type
        mime = message.audio.mime_type or "audio/mpeg"
        ext_map = {
            "audio/mpeg": ".mp3",
            "audio/ogg": ".ogg",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/flac": ".flac",
            "audio/aac": ".aac",
            "audio/mp4": ".m4a",
            "audio/webm": ".webm",
        }
        suffix = ext_map.get(mime, ".mp3")
        filename = f"audio{suffix}"

    logger.info(
        "Audio file from %s: %s",
        message.from_user.id,
        filename,
    )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        audio_path = Path(tmp.name)

    try:
        await _download_file(bot, file_obj, audio_path)
        await _process_audio_file(message, bot, audio_path, source_name=filename)
    finally:
        try:
            audio_path.unlink()
        except OSError:
            pass


# ── Core processing ─────────────────────────────────────────────────


async def _process_audio_file(
    message: Message,
    bot: Bot,
    audio_path: Path,
    source_name: str = "audio",
) -> None:
    """Download, transcribe, and reply for an audio file."""
    duration_ms = _get_audio_duration_ms(audio_path)

    if duration_ms == 0:
        await message.answer(_format_error("Could not read audio file\\."), parse_mode=ParseMode.MARKDOWN_V2)
        return

    logger.info("Processing %s (duration=%dms)", source_name, duration_ms)

    async with httpx.AsyncClient() as client:
        if duration_ms <= LONG_AUDIO_THRESHOLD_MS:
            await _process_short(client, message, bot, audio_path, duration_ms)
        else:
            await _process_long(client, message, bot, audio_path, duration_ms)


async def _process_short(
    client: httpx.AsyncClient,
    message: Message,
    bot: Bot,
    audio_path: Path,
    duration_ms: int,
) -> None:
    """Transcribe short audio in a single request."""
    status_msg = await message.answer("🎙 Transcribing\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)

    result = await _transcribe_single(client, audio_path)

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
    except Exception:
        pass

    if result is None:
        await message.answer(
            _format_error("Transcription failed\\. Please try again later\\."),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    text = result.get("text", "")
    segments = result.get("segments", [])
    reply = _format_transcript(text, duration_ms)

    await message.answer(reply, parse_mode=ParseMode.MARKDOWN_V2)


async def _send_long_message(
    message: Message,
    header: str,
    escaped_text: str,
) -> None:
    """Send text split across multiple Telegram messages if it exceeds 4096 chars."""
    MAX_LEN = 4096
    header_line = header + "\n\n"
    header_len = len(header_line)

    if header_len + len(escaped_text) <= MAX_LEN:
        # Fits in one message
        await message.answer(header_line + escaped_text, parse_mode=ParseMode.MARKDOWN_V2)
        return

    # First message includes header + as much text as fits
    first_chunk = escaped_text[: MAX_LEN - header_len]
    await message.answer(header_line + first_chunk, parse_mode=ParseMode.MARKDOWN_V2)

    # Remaining chunks as follow-up messages
    remaining = escaped_text[MAX_LEN - header_len :]
    # Split on newline boundaries when possible
    while remaining:
        chunk = remaining[:MAX_LEN]
        # Try to break at a newline
        if len(remaining) > MAX_LEN:
            last_nl = chunk.rfind("\n")
            if last_nl > MAX_LEN // 2:
                chunk = chunk[:last_nl]
        remaining = remaining[len(chunk):]
        await message.answer(chunk, parse_mode=ParseMode.MARKDOWN_V2)


async def _process_long(
    client: httpx.AsyncClient,
    message: Message,
    bot: Bot,
    audio_path: Path,
    duration_ms: int,
) -> None:
    """Transcribe long audio by splitting into chunks with progressive updates."""
    chunks = _split_audio_chunks(audio_path)
    total_chunks = len(chunks)

    logger.info(
        "Long audio: %dms → %d chunks",
        duration_ms,
        total_chunks,
    )

    # Send initial progress message
    progress_msg = await message.answer(
        f"📝 Transcribing \\(0/{total_chunks} chunks\\)\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    full_text = ""
    all_segments: list[dict] = []
    segment_offset_ms: int = 0

    try:
        for i, chunk_path in enumerate(chunks):
            result = await _transcribe_single(client, chunk_path)

            if result is None:
                # Update progress with error info
                try:
                    await progress_msg.edit_text(
                        f"❌ Chunk {i + 1}/{total_chunks} failed\\. Transcription incomplete\\.",
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
                except Exception:
                    pass
                return

            chunk_text = result.get("text", "")
            chunk_segments = result.get("segments", [])

            # Adjust segment timestamps by the current offset
            for seg in chunk_segments:
                seg["start_ms"] = seg.get("start", 0) * 1000 + segment_offset_ms
                seg["end_ms"] = seg.get("end", 0) * 1000 + segment_offset_ms
                seg["text"] = seg.get("text", "")

            # Merge text with overlap deduplication
            if i == 0:
                full_text = chunk_text.strip()
            else:
                full_text = _merge_chunk_text(full_text, chunk_text)

            all_segments.extend(chunk_segments)

            # Calculate offset for next chunk.
            # Chunk i starts at position i * (CHUNK_DURATION_MS - CHUNK_OVERLAP_MS)
            # in the original audio (same as the splitting loop).
            segment_offset_ms = (i + 1) * (CHUNK_DURATION_MS - CHUNK_OVERLAP_MS)

            # Update progress message
            escaped_text = _escape_telegram(full_text)
            status_line = f"📝 *Transcript* \\({i + 1}/{total_chunks} chunks\\)\n\n"
            # Truncate progressive update to fit single message
            max_content = 4096 - len(status_line) - 10
            display_text = escaped_text[:max_content] + "\\.\\.\\." if len(escaped_text) > max_content else escaped_text

            try:
                await progress_msg.edit_text(
                    status_line + display_text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            except Exception:
                pass

    finally:
        # Clean up temp chunk files
        for chunk_path in chunks:
            try:
                chunk_path.unlink()
            except OSError:
                pass

    # Final update — split into multiple messages if needed
    duration_s = duration_ms / 1000
    mins = int(duration_s // 60)
    secs = int(duration_s % 60)

    header = f"📝 *Transcript* _{mins}:{secs:02d}_"
    final_escaped = _escape_telegram(full_text)

    # Delete the progress message; send final transcript as new message(s)
    try:
        await progress_msg.delete()
    except Exception:
        pass

    await _send_long_message(message, header, final_escaped)


# ── Unknown message handler ─────────────────────────────────────────


@router.message()
async def handle_unknown(message: Message) -> None:
    """Handle messages that aren't voice/audio/commands."""
    if message.from_user is None:
        return
    if not _is_allowed(message.from_user.id):
        return
    await message.answer(
        "Send me a voice message or audio file to transcribe\\. "
        "Use /help for more info\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ── Main ────────────────────────────────────────────────────────────


async def main() -> None:
    """Start the bot with polling."""
    _validate_config()

    # Configure local Telegram API server if available (files >20 MB)
    bot_kwargs: dict = {
        "token": TELEGRAM_TOKEN,
        "default": DefaultBotProperties(parse_mode=ParseMode.MARKDOWN_V2),
    }
    if TELEGRAM_API_URL:
        from aiogram.client.session.aiohttp import AiohttpSession
        from aiogram.client.telegram import TelegramAPIServer

        api = TelegramAPIServer.from_base(TELEGRAM_API_URL)
        session = AiohttpSession(api=api)
        bot_kwargs["session"] = session
        logger.info("Using local Telegram API server: %s", TELEGRAM_API_URL)

    bot = Bot(**bot_kwargs)
    dp = Dispatcher()
    dp.include_router(router)

    logger.info(
        "Bot starting — allowed users: %s, nanoscribe: %s",
        len(ALLOWED_UIDS),
        NANOSCRIBE_URL,
    )

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
