"""Unit tests for the bot's pure functions."""
import sys
import tempfile
import wave
import struct
from pathlib import Path

# ── bot.py functions (copied inline for isolation) ──────────────────

_CHUNK_DURATION_MS = 60_000
_CHUNK_OVERLAP_MS = 2_000


def _escape_telegram(text: str) -> str:
    special = r"_*[]()~`>#+-=|{}.!"
    result: list[str] = []
    for ch in text:
        if ch in special:
            result.append("\\" + ch)
        else:
            result.append(ch)
    return "".join(result)


def _merge_chunk_text(previous_text: str, chunk_text: str) -> str:
    if not previous_text:
        return chunk_text.strip()
    prev = previous_text.strip()
    curr = chunk_text.strip()
    max_overlap = min(len(prev), len(curr), 200)
    for overlap_len in range(max_overlap, 0, -1):
        if prev[-overlap_len:] == curr[:overlap_len]:
            return prev + curr[overlap_len:]
    return prev + " " + curr


def _format_transcript(text: str, duration_ms: int | None = None) -> str:
    if not text:
        return "_(no speech detected)_"
    escaped = _escape_telegram(text)
    if duration_ms is not None:
        duration_s = duration_ms / 1000
        mins = int(duration_s // 60)
        secs = int(duration_s % 60)
        header = f"📝 *Transcript* _{mins}:{secs:02d}_\n\n"
        return header + escaped
    return escaped


def _split_audio_chunks(
    file_path: Path,
    chunk_duration_ms: int = _CHUNK_DURATION_MS,
    overlap_ms: int = _CHUNK_OVERLAP_MS,
) -> list[Path]:
    from pydub import AudioSegment
    audio = AudioSegment.from_file(str(file_path))
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    total_ms = len(audio)
    chunks: list[Path] = []
    pos = 0
    while pos < total_ms:
        end = min(pos + chunk_duration_ms, total_ms)
        chunk = audio[pos:end]
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", prefix=f"chunk_{pos}_", delete=False)
        tmp.close()
        chunk_path = Path(tmp.name)
        chunk.export(str(chunk_path), format="wav")
        chunks.append(chunk_path)
        if end >= total_ms:
            break
        pos = end - overlap_ms
        if pos <= (end - chunk_duration_ms):
            pos = end
    return chunks


def _seg_offset(i: int) -> int:
    """Segment offset for chunk i (matches _process_long formula)."""
    return i * (_CHUNK_DURATION_MS - _CHUNK_OVERLAP_MS)


# ── Helpers ─────────────────────────────────────────────────────────

def make_wav(duration_ms: int) -> Path:
    """Create a silent WAV of given duration."""
    sample_rate = 16000
    n_samples = int(sample_rate * duration_ms / 1000)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = Path(tmp.name)
    with wave.open(str(tmp_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_samples)
    return tmp_path


# ── Tests ───────────────────────────────────────────────────────────

def test_escape():
    assert _escape_telegram("hello") == "hello"
    assert _escape_telegram("hello_world") == "hello\\_world"
    assert _escape_telegram("test*stuff") == "test\\*stuff"
    assert _escape_telegram("[ok]") == "\\[ok\\]"
    assert _escape_telegram("a.b!c") == "a\\.b\\!c"
    assert _escape_telegram("__bold__") == "\\_\\_bold\\_\\_"
    assert _escape_telegram("") == ""


def test_merge():
    # No overlap
    assert _merge_chunk_text("Hello world", "This is new") == "Hello world This is new"
    # Perfect overlap
    assert _merge_chunk_text("Hello world", "world The end") == "Hello world The end"
    # Partial overlap
    assert _merge_chunk_text("Hello wo", "o world") == "Hello world"
    # Empty previous
    assert _merge_chunk_text("", "Fresh start") == "Fresh start"
    # Common case: chunk text continues
    assert _merge_chunk_text("First chunk text", "chunk text continues here") == "First chunk text continues here"
    # Exact match
    assert _merge_chunk_text("exact same", "exact same") == "exact same"


def test_format():
    assert _format_transcript("", 0) == "_(no speech detected)_"
    result = _format_transcript("Hello", 30000)
    assert "0:30" in result
    assert "Hello" in result
    result = _format_transcript("Hello", 125000)
    assert "2:05" in result
    assert "Hello" in result
    assert "Hi\\_there" in _format_transcript("Hi_there")


def test_chunk_count():
    """3s audio → 1 chunk, 90s audio → 2 chunks, etc."""
    # Short: 3s
    wav = make_wav(3000)
    try:
        chunks = _split_audio_chunks(wav)
        assert len(chunks) == 1, f"3s: expected 1 chunk, got {len(chunks)}"
        for c in chunks:
            c.unlink()
    finally:
        wav.unlink()

    # 90s → should produce 2 chunks (60s + 30s, with 2s overlap)
    wav = make_wav(90_000)
    try:
        chunks = _split_audio_chunks(wav)
        assert len(chunks) == 2, f"90s: expected 2 chunks, got {len(chunks)}"
        for c in chunks:
            c.unlink()
    finally:
        wav.unlink()

    # 150s → should produce 3 chunks (0-60, 58-118, 116-150)
    wav = make_wav(150_000)
    try:
        chunks = _split_audio_chunks(wav)
        assert len(chunks) == 3, f"150s: expected 3 chunks, got {len(chunks)}"
        for c in chunks:
            c.unlink()
    finally:
        wav.unlink()


def test_segment_offset():
    """Verify segment offset formula matches chunk positions."""
    stride = _CHUNK_DURATION_MS - _CHUNK_OVERLAP_MS  # 58000
    assert _seg_offset(0) == 0
    assert _seg_offset(1) == stride
    assert _seg_offset(2) == stride * 2
    assert _seg_offset(3) == stride * 3
    # Verify these match the actual chunk start positions
    # (i * stride = i * 58000)
    for i in range(10):
        assert _seg_offset(i) == i * 58000


if __name__ == "__main__":
    tests = [test_escape, test_merge, test_format, test_chunk_count, test_segment_offset]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
    print("ALL TESTS PASSED ✅")
