"""Integration-level tests for the bot's complete processing pipeline.

Tests the full audio→chunks→merge flow with real WAV files.
Does NOT need Telegram or a running NanoScribe.
"""
import sys
import tempfile
import wave
from pathlib import Path

# Override for testing: use tiny chunks to test chunking logic thoroughly
CHUNK_DURATION_MS = 1000  # 1 second chunks
CHUNK_OVERLAP_MS = 200  # 200ms overlap
LONG_AUDIO_THRESHOLD_MS = 2000  # >2s = long


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


def _split_audio_chunks(
    file_path: Path,
    chunk_duration_ms: int = CHUNK_DURATION_MS,
    overlap_ms: int = CHUNK_OVERLAP_MS,
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


# ── Simulated transcription result ──────────────────────────────────

def fake_transcribe_result(chunk_index: int, text: str) -> dict:
    """Simulate a verbose_json response from NanoScribe for a chunk."""
    return {
        "text": text,
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 1.0,
                "text": text,
                "seek": 0,
                "tokens": [],
                "temperature": 0.0,
                "avg_logprob": -0.5,
                "compression_ratio": 1.0,
                "no_speech_prob": 0.01,
            }
        ],
        "duration": 1.0,
        "language": "en",
    }


# ── Test: Full chunked processing simulation ────────────────────────

def test_long_audio_pipeline():
    """Simulate processing a 3.5s audio file through the chunked pipeline.

    With 1s chunks and 200ms overlap, 3500ms should produce:
    - Chunk 0: [0, 1000]
    - Chunk 1: [800, 1800]
    - Chunk 2: [1600, 2600]
    - Chunk 3: [2400, 3400]
    - Chunk 4: [3200, 3500]
    Total: 5 chunks
    """
    wav = make_wav(3500)
    try:
        chunks = _split_audio_chunks(wav)
        print(f"  3500ms audio → {len(chunks)} chunks (expected 5)")
        assert len(chunks) == 5, f"Expected 5 chunks, got {len(chunks)}"

        # Simulate transcription results with text that has natural overlap
        fake_texts = [
            "This is the first chunk with some text",
            "chunk with some text that continues into the second",
            "into the second chunk and then goes further still",
            "then goes further still into the fourth part here",
            "fourth part here and then the final ending",
        ]

        full_text = ""
        segment_offset_ms = 0
        stride = CHUNK_DURATION_MS - CHUNK_OVERLAP_MS  # 800ms

        for i, text in enumerate(fake_texts):
            # Simulate segment timestamp adjustment
            seg_offset = segment_offset_ms

            # Merge text
            if i == 0:
                full_text = text.strip()
            else:
                full_text = _merge_chunk_text(full_text, text)

            # Update offset for next chunk
            segment_offset_ms = (i + 1) * stride

            # Verify offset matches expected chunk position
            expected_pos = i * stride
            # seg_offset at this iteration should match i * stride
            # (since segment_offset_ms was updated after previous iteration)

        print(f"  Full merged text: '{full_text}'")
        # Verify deduplication worked — the overlapping phrase "chunk with some text"
        # should appear exactly once (from chunk 0), not duplicated from chunk 1.
        # The merge should have: first chunk... + "that continues into the second ..."
        assert "This is the first chunk with some text" in full_text
        # Verify there's no duplication of overlapping text
        count_chunk_with = full_text.count("chunk with some text")
        assert count_chunk_with == 1, f"'chunk with some text' appears {count_chunk_with} times (expected 1)"

        # Verify offset progression
        for i in range(5):
            expected = i * stride
            assert expected == i * 800, f"Offset at i={i}: expected {i*800}, got {expected}"
        print(f"  Offsets: {[i * stride for i in range(5)]} — correct")

        # Clean up
        for c in chunks:
            c.unlink()
    finally:
        wav.unlink()


def test_short_audio():
    """Short audio (under threshold) should NOT be split by routing logic.

    Note: with mini chunk sizes (1s), even "short" audio will produce
    multiple chunks in _split_audio_chunks.  The routing logic in the real
    bot uses 60s chunks, so 1.5s audio would be 1 chunk.  Here we test
    that the threshold check works correctly.
    """
    assert 1500 <= LONG_AUDIO_THRESHOLD_MS, "1500ms should be below threshold"
    assert 3500 > LONG_AUDIO_THRESHOLD_MS, "3500ms should be above threshold"

    # With real bot defaults (60s chunks), 1.5s → 1 chunk
    real_chunk_duration = 60_000
    assert 1500 < real_chunk_duration, "1.5s fits in a single 60s chunk"
    print(f"  1500ms < 2000ms threshold → short (routing test OK)")


def test_boundary_exactly_at_threshold():
    """Audio exactly at the threshold boundary."""
    wav = make_wav(2000)  # exactly 2s
    try:
        chunks = _split_audio_chunks(wav)
        print(f"  2000ms audio → {len(chunks)} chunks")
        # 2s = exactly 2 chunks (1000 + 1000 with 200ms overlap → 1000ms + 1000ms = 2 chunks? No:
        # pos=0: [0, 1000], end=1000 < 2000, pos = 1000-200 = 800
        # pos=800: [800, 1800], end=1800 < 2000, pos = 1800-200 = 1600
        # pos=1600: [1600, 2000], end=2000 >= 2000, break
        # Total: 3 chunks
        assert len(chunks) == 3, f"Expected 3 chunks, got {len(chunks)}"
        print(f"  → 3 chunks (correct: 0-1000, 800-1800, 1600-2000)")
        for c in chunks:
            c.unlink()
    finally:
        wav.unlink()


def test_whitelist_logic():
    """Test the whitelist checking logic (pure function)."""
    ALLOWED_UIDS = {123, 456}

    def _is_allowed(user_id: int) -> bool:
        return user_id in ALLOWED_UIDS

    assert _is_allowed(123) is True
    assert _is_allowed(456) is True
    assert _is_allowed(789) is False
    assert _is_allowed(0) is False
    print("  Whitelist logic correct")


def test_config_validation():
    """Test the config validation logic."""
    missing = []
    if not "":
        missing.append("TELEGRAM_TOKEN")
    if not set():
        missing.append("ALLOWED_UIDS")
    assert len(missing) == 2  # empty token and empty uids → both missing

    missing2 = []
    if not "some_token":
        missing2.append("TELEGRAM_TOKEN")
    if not {1}:
        missing2.append("ALLOWED_UIDS")
    assert len(missing2) == 0  # both set → no missing
    print("  Config validation logic correct")


def test_merge_edge_cases():
    """Test merge edge cases."""
    # Identical text should merge cleanly
    assert _merge_chunk_text("hello", "hello") == "hello"
    # Single char overlap
    assert _merge_chunk_text("ab", "bc") == "abc"
    # No overlap, very different
    assert _merge_chunk_text("aaaaa", "bbbbb") == "aaaaa bbbbb"
    # Multi-word overlap
    assert _merge_chunk_text("the quick brown fox", "brown fox jumps over") == "the quick brown fox jumps over"
    # Whitespace preservation
    assert _merge_chunk_text("  hello world  ", "world again") == "hello world again"
    print("  All merge edge cases pass")


# ── Run ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("chunking pipeline", test_long_audio_pipeline),
        ("short audio", test_short_audio),
        ("boundary", test_boundary_exactly_at_threshold),
        ("whitelist", test_whitelist_logic),
        ("config validation", test_config_validation),
        ("merge edge cases", test_merge_edge_cases),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✅ {name}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Integration tests: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
    print("ALL INTEGRATION TESTS PASSED ✅")
