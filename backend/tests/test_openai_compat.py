"""HTTP response contracts for the OpenAI-compatible transcription endpoint."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import openai_compat


@pytest.mark.parametrize("response_format", ["json", "verbose_json", "text", "srt", "vtt"])
def test_transcription_response_formats(monkeypatch, response_format):
    models = Mock()
    models.transcribe.return_value = {
        "text": "Hello 世界",
        "segments": [{"start_ms": 0, "end_ms": 1000, "text": "Hello 世界"}],
        "raw_output": [],
    }
    monkeypatch.setattr(openai_compat, "get_models", lambda: models)
    monkeypatch.setattr(openai_compat, "normalize_audio", lambda source, directory: source)
    monkeypatch.setattr(openai_compat, "extract_duration_ms", lambda path: 1000)
    monkeypatch.setattr(openai_compat, "_settings", Mock(api_key=""))
    app = FastAPI()
    app.include_router(openai_compat.router)

    response = TestClient(app).post(
        "/v1/audio/transcriptions",
        files={"file": ("audio.wav", b"audio", "audio/wav")},
        data={"response_format": response_format},
    )

    assert response.status_code == 200
    if response_format == "json":
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"text": "Hello 世界"}
    elif response_format == "verbose_json":
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {
            "task": "transcribe",
            "language": "en",
            "duration": 1.0,
            "text": "Hello 世界",
            "words": [],
            "segments": [
                {
                    "id": 0,
                    "seek": 0.0,
                    "start": 0.0,
                    "end": 1.0,
                    "text": "Hello 世界",
                    "tokens": [],
                    "temperature": 0.0,
                    "avg_logprob": 0.0,
                    "compression_ratio": 0.0,
                    "no_speech_prob": 0.0,
                }
            ],
        }
    elif response_format == "text":
        assert response.headers["content-type"].startswith("text/plain")
        assert response.text == "Hello 世界"
    else:
        assert response.headers["content-type"].startswith("text/" + response_format)
        assert "Hello 世界" in response.text
        assert (
            "00:00:00,000 --> 00:00:01,000" if response_format == "srt" else "00:00:00.000 --> 00:00:01.000"
        ) in response.text
